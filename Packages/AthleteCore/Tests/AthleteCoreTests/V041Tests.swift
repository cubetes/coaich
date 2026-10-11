import Foundation
import Testing
@testable import AthleteCore

// v0.4.1: Live Activity design D (G32–G37) — the workout bar and the one rest-vs-set rule.

private let t0 = Date(timeIntervalSince1970: 1_791_429_164)

private func slot(reps: String, template: String? = "T") -> Plan.Slot {
    let id = template.map { #""\#($0)""# } ?? "null"
    let json = #"{"name": "X", "template_id": \#(id), "prescription": {"sets": 3}, "target": {"kg": 100, "reps": "\#(reps)"}}"#
    return try! Plan.decoder.decode(Plan.Slot.self, from: Data(json.utf8))
}

private func log(_ s: inout Session, _ key: String, type: Session.SetType = .normal) {
    s.confirm(slot: key, templateId: "T", title: "X", planned: PlannedSet(weightKg: 100, reps: 8),
              weightKg: 100, reps: 8, type: type, at: t0)
}

@Test func workoutBarHasOneSegmentPerExerciseSizedByPlannedSets() {
    let plan = Plan(routines: ["a": .init(title: "A", slots: ["a/x", "a/y", "a/z", "a/nolog"])],
                    slots: ["a/x": slot(reps: "8·8·8·8"), "a/y": slot(reps: "10·10·10"),
                            "a/z": slot(reps: "12·12·12"), "a/nolog": slot(reps: "8", template: nil)])
    var s = Session(routineTitle: "A", startedAt: t0)
    log(&s, "a/y", type: .warmup)                 // warm-ups count for nothing
    log(&s, "a/y"); log(&s, "a/y")
    for _ in 0..<5 { log(&s, "a/x") }             // a "+1 serie" beyond the plan never overfills
    let seg = plan.segments(routineKey: "a", session: s, added: [:])
    #expect(seg == [.init(planned: 4, done: 4), .init(planned: 3, done: 2), .init(planned: 3, done: 0)]) // unloggable slot left out
    #expect(plan.segments(routineKey: "a", session: nil, added: [:]).allSatisfy { $0.done == 0 })
}

@Test func aRestWhoseEndPassedIsOver() {
    let s = LiveState(routineTitle: "A", startedAt: t0, restEnd: t0.addingTimeInterval(60))
    #expect(s.isResting(at: t0))
    #expect(!s.isResting(at: t0.addingTimeInterval(60)))  // never "Descanso" over a session clock (LA-03)
    #expect(!LiveState(routineTitle: "A", startedAt: t0).isResting(at: t0))
}

@Test func newFieldsRoundTripAndOldMessagesStillDecode() throws {
    let s = LiveState(routineTitle: "A", startedAt: t0, restEnd: t0.addingTimeInterval(90), restStart: t0,
                      targetKg: 102.5, targetReps: 8, warmup: false, segments: [.init(planned: 4, done: 2)], current: 0)
    #expect(try LiveState.decode(s.encoded()) == s)
    let old = #"{"routineTitle":"A","startedAt":0,"setsLogged":3,"ended":false}"#
    #expect(try LiveState.decode(Data(old.utf8)).segments == nil)   // a v0.4.0 Watch talking to a v0.4.1 phone
}

// MARK: - The Watch's LiveState builder (red team must-fix 7)

private let livePlan: Plan = {
    let x = #"{"name": "Press banca inclinado", "short_name": "Banca incl.", "template_id": "T", "prescription": {"sets": 2, "rest_s": 120}, "target": {"kg": 100, "reps": "8·8"}}"#
    let y = #"{"name": "Aperturas", "template_id": "T", "prescription": {"sets": 1}, "target": {"kg": 20, "reps": "12"}}"#
    return Plan(routines: ["a": .init(title: "Push A", slots: ["a/x", "a/y"])],
                slots: ["a/x": try! Plan.decoder.decode(Plan.Slot.self, from: Data(x.utf8)),
                        "a/y": try! Plan.decoder.decode(Plan.Slot.self, from: Data(y.utf8))])
}()

/// The Watch's draft for `slot` as `syncDraft` leaves it.
private func draft(_ s: Session, _ slot: String, type: Session.SetType = .normal) -> Draft {
    var d = Draft()
    d.sync(slot: slot, confirmed: s.sets(forSlot: slot).count, added: 0,
           prefill: livePlan.slots[slot]!.prefill(confirmed: s.sets(forSlot: slot), added: 0))
    d.type = type
    return d
}

private func live(_ s: Session?, slot: String?, draft d: Draft = Draft(), rest: Bool = false, go: Date? = nil) -> LiveState? {
    LiveState.watch(plan: livePlan, routineKey: "a", session: s, slot: slot, added: [:], draft: d,
                    restStart: t0, restEnd: rest ? t0.addingTimeInterval(90) : nil, go: go)
}

@Test func shortNameDecodesAndIsOptional() throws {
    #expect(livePlan.slots["a/x"]?.shortName == "Banca incl.")
    #expect(livePlan.slots["a/y"]?.shortName == nil)
    let back = try Plan.decoder.decode(Plan.self, from: Plan.encoder.encode(livePlan)) // the phone → Watch hop keeps it
    #expect(back.slots["a/x"]?.shortName == "Banca incl.")
}

@Test func duringTheCountdownOnlyTheRoutineAndAnEmptyBar() {
    let go = t0.addingTimeInterval(3)
    let s = live(nil, slot: nil, go: go)!
    #expect(s.routineTitle == "Push A" && s.go == go && s.startedAt == go)
    #expect(s.exercise == nil && s.targetKg == nil && s.current == nil)
    #expect(s.segments == [.init(planned: 2, done: 0), .init(planned: 1, done: 0)])
    #expect(live(nil, slot: nil) == nil)  // no session, no countdown: nothing to send
}

@Test func liveSetCarriesTheDraftAndShortName() {
    let s = Session(routineTitle: "Push A", startedAt: t0)
    var d = draft(s, "a/x")
    d.kg = 102.5                          // a Crown edit: the target is what Hecho would log
    let st = live(s, slot: "a/x", draft: d)!
    #expect(st.exercise == "Banca incl." && st.setNumber == 1 && st.setsPlanned == 2)
    #expect(st.targetKg == 102.5 && st.targetReps == 8 && st.warmup == false && st.current == 0)
    #expect(st.restStart == nil && st.go == nil)
}

@Test func warmupHasNoSetNumber() {
    let s = Session(routineTitle: "Push A", startedAt: t0)
    let st = live(s, slot: "a/x", draft: draft(s, "a/x", type: .warmup))!
    #expect(st.warmup == true && st.setNumber == nil && st.exercise == "Banca incl.")
}

@Test func afterTheLastSetOfAnExerciseTheStateNamesTheNextOne() {
    var s = Session(routineTitle: "Push A", startedAt: t0)
    log(&s, "a/x"); log(&s, "a/x")       // confirm() then moves currentSlot to a/y
    let st = live(s, slot: "a/y", draft: draft(s, "a/y"), rest: true)!
    #expect(st.exercise == "Aperturas" && st.setNumber == 1 && st.setsPlanned == 1)   // G36 "Siguiente"
    #expect(st.targetKg == 20 && st.targetReps == 12 && st.current == 1)
    #expect(st.restStart == t0 && st.isResting(at: t0))
    #expect(st.segments == [.init(planned: 2, done: 2), .init(planned: 1, done: 0)])
}

@Test func afterTheRoutinesLastSetNothingIsNextAndTheBarIsFull() {
    var s = Session(routineTitle: "Push A", startedAt: t0)
    log(&s, "a/x"); log(&s, "a/x"); log(&s, "a/y")   // currentSlot stays on a/y
    let st = live(s, slot: "a/y", draft: draft(s, "a/y"), rest: true)!
    #expect(st.exercise == nil && st.setNumber == nil && st.targetKg == nil && st.warmup == nil && st.current == nil)
    #expect(st.segments!.allSatisfy { $0.done == $0.planned })   // "Todo hecho" (LA-06)
    #expect(st.setsLogged == 3 && st.isResting(at: t0))
    #expect(live(s, slot: "a/y", draft: draft(s, "a/y"))!.restStart == nil) // rest over: no stale restStart
}

@Test func unlogAndDeshacerMoveTheSetNumberBackAndForth() {
    var s = Session(routineTitle: "Push A", startedAt: t0)
    log(&s, "a/x"); log(&s, "a/x")
    let before = live(s, slot: "a/x", draft: draft(s, "a/x"))!
    #expect(before.exercise == nil)        // a/x finished and left open: nothing to log on it
    let u = s.unlog(slot: "a/x", index: 1)!
    let unlogged = live(s, slot: "a/x", draft: draft(s, "a/x"))!
    #expect(unlogged.setNumber == 2 && unlogged.targetKg == 100 && unlogged.segments?[0].done == 1)
    s.restore(u)
    #expect(live(s, slot: "a/x", draft: draft(s, "a/x")) == before)   // Deshacer: exactly the state before
}
