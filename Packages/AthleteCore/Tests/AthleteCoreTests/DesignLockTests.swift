import Foundation
import Testing
@testable import AthleteCore

// Rules from the design lock (docs/design/DESIGN.md, scope L1–L8, SYNTHESIS must-fixes).

private let t0 = Date(timeIntervalSince1970: 1_791_429_164)

private func slot(kg: Double?, reps: String?, sets: Int = 3, equipment: String? = nil) -> Plan.Slot {
    let target = kg.map { #"{"kg": \#($0), "reps": "\#(reps ?? "")"}"# } ?? "null"
    let json = #"{"name": "X", "template_id": "T", "prescription": {"sets": \#(sets)}, "target": \#(target)\#(equipment.map { #", "equipment": "\#($0)""# } ?? "")}"#
    return try! Plan.decoder.decode(Plan.Slot.self, from: Data(json.utf8))
}

private func log(_ s: inout Session, kg: Double, reps: Int, type: Session.SetType = .normal, planned: PlannedSet) {
    s.confirm(slot: "a/x", templateId: "T", title: "X", planned: planned, weightKg: kg, reps: reps, type: type, at: t0)
}

// MARK: Must-fix 2 — the edited weight carries forward

@Test func editedWeightCarriesToTheNextPlannedSet() {
    let x = slot(kg: 100, reps: "12·12·10")
    var s = Session(routineTitle: "A", startedAt: t0)
    log(&s, kg: 102.5, reps: 12, planned: x.prefill(confirmed: [], added: 0)!)
    let next = x.prefill(confirmed: s.sets(forSlot: "a/x"), added: 0)
    #expect(next == PlannedSet(weightKg: 102.5, reps: 12)) // kg from the bar, reps from the plan
    log(&s, kg: 102.5, reps: 12, planned: next!)
    #expect(s.sets(forSlot: "a/x")[1].unedited) // lifted what was shown
    #expect(x.prefill(confirmed: s.sets(forSlot: "a/x"), added: 0) == PlannedSet(weightKg: 102.5, reps: 10))
}

@Test func warmUpWeightNeverCarriesForward() {
    let x = slot(kg: 100, reps: "10·10")
    var s = Session(routineTitle: "A", startedAt: t0)
    log(&s, kg: 60, reps: 8, type: .warmup, planned: PlannedSet(weightKg: 100, reps: 10))
    #expect(x.prefill(confirmed: s.sets(forSlot: "a/x"), added: 0) == PlannedSet(weightKg: 100, reps: 10))
}

@Test func noTargetCopiesTheLastSet() {
    let x = slot(kg: nil, reps: nil)
    var s = Session(routineTitle: "A", startedAt: t0)
    #expect(x.prefill(confirmed: [], added: 0) == PlannedSet(weightKg: nil, reps: nil))
    log(&s, kg: 25, reps: 11, planned: PlannedSet(weightKg: nil, reps: nil))
    #expect(x.prefill(confirmed: s.sets(forSlot: "a/x"), added: 0) == PlannedSet(weightKg: 25, reps: 11))
}

// MARK: L3 — loadability warning (barbell only)

@Test func barbellWeightsThatCantBeLoadedWarn() {
    #expect(PlateMath.unloadablePerSide(total: 101.25, startWeight: 20) == 0.625)
    #expect(PlateMath.unloadablePerSide(total: 102.5, startWeight: 20) == nil)
    #expect(PlateMath.startWeight(equipment: "dumbbell") == nil) // no plates: no warning
    #expect(PlateMath.startWeight(equipment: nil) == nil) // older snapshot: no warning
    #expect(PlateMath.unloadablePerSide(total: 20, startWeight: 20) == nil) // empty bar
}

@Test func equipmentDecodesWhenPresent() {
    #expect(slot(kg: 100, reps: "10", equipment: "barbell").equipment == "barbell")
    #expect(slot(kg: 100, reps: "10").equipment == nil)
}

// MARK: Must-fix 5 — keypad and Crown bounds

@Test func keypadBounds() {
    #expect(Entry.keypad("102,5", isReps: false) == 102.5)
    #expect(Entry.keypad("0", isReps: false) == 0)
    #expect(Entry.keypad("600", isReps: false) == 600)
    #expect(Entry.keypad("1025", isReps: false) == nil) // missed comma
    #expect(Entry.keypad("12", isReps: true) == 12)
    #expect(Entry.keypad("0", isReps: true) == nil)
    #expect(Entry.keypad("120", isReps: true) == nil)
    #expect(Entry.keypad("10,5", isReps: true) == nil)
    #expect(Entry.keypad("", isReps: true) == nil)
}

@Test func crownStepsAreClamped() {
    #expect(Entry.step(kg: 100, by: 1, equipment: nil) == 101.25)
    #expect(Entry.step(kg: 1.25, by: -3, equipment: nil) == 0)
    #expect(Entry.step(kg: 599, by: 4, equipment: nil) == 600)
    #expect(Entry.step(reps: 1, by: -2) == 1)
    #expect(Entry.step(reps: 99, by: 5) == 100)
}

// MARK: Must-fix 5 + L8 — edit any confirmed set

@Test func editAnyConfirmedSetKeepsItsPlaceAndTime() {
    var s = Session(routineTitle: "A", startedAt: t0)
    let p = PlannedSet(weightKg: 100, reps: 12)
    log(&s, kg: 100, reps: 12, planned: p)
    log(&s, kg: 100, reps: 12, planned: p)
    let rev = s.rev
    let ok1 = s.editSet(slot: "a/x", index: 0, weightKg: 100, reps: 10, type: .failure)
    #expect(ok1)
    let first = s.sets(forSlot: "a/x")[0]
    #expect(first.reps == 10 && first.type == .failure && !first.unedited && first.index == 0 && first.doneAt == t0)
    #expect(s.sets(forSlot: "a/x").count == 2) // never duplicates
    #expect(s.rev == rev + 1)
    s.editSet(slot: "a/x", index: 0, weightKg: 100, reps: 10, type: .failure) // nothing changed
    #expect(s.rev == rev + 1)
    let ok2 = s.editSet(slot: "a/x", index: 1, weightKg: 100, reps: 12, type: .warmup)
    #expect(ok2)
    #expect(s.sets(forSlot: "a/x")[1].unedited) // only a type change: numbers still as shown
    let bad1 = s.editSet(slot: "a/x", index: 1, weightKg: 1025, reps: 12, type: .normal) // out of bounds
    let bad2 = s.editSet(slot: "a/x", index: 1, weightKg: 100, reps: 0, type: .normal)
    #expect(!bad1 && !bad2)
    #expect(s.sets(forSlot: "a/x")[1].weightKg == 100)
}

@Test func deletingAPastSetReindexes() {
    var s = Session(routineTitle: "A", startedAt: t0)
    let p = PlannedSet(weightKg: 100, reps: 12)
    for r in [12, 11, 10] { log(&s, kg: 100, reps: r, planned: p) }
    s.deleteSet(slot: "a/x", index: 0)
    #expect(s.sets(forSlot: "a/x").map(\.index) == [0, 1])
    #expect(s.sets(forSlot: "a/x").map(\.reps) == [11, 10])
}

@Test func setNavigatorWalksConfirmedSetsOnly() {
    var nav = SetNavigator()
    #expect(nav.isLive && !nav.canGoForward)
    #expect(!nav.canGoBack(confirmed: 0)) // first set: nothing behind
    nav.back(confirmed: 0)
    #expect(nav.isLive)
    nav.back(confirmed: 2)
    #expect(nav.editing == 1 && !nav.isLive && nav.canGoForward)
    nav.back(confirmed: 2)
    #expect(nav.editing == 0 && !nav.canGoBack(confirmed: 2))
    nav.back(confirmed: 2)
    #expect(nav.editing == 0) // disabled at the start
    nav.forward(confirmed: 2)
    #expect(nav.editing == 1)
    nav.forward(confirmed: 2)
    #expect(nav.isLive) // forward stops at the live set, never previews later planned sets
    nav.forward(confirmed: 2)
    #expect(nav.isLive)
    nav.back(confirmed: 2); nav.reset()
    #expect(nav.isLive)
}

// MARK: Must-fix 6 — RIR never clears silently

@Test func secondTapOnTheSelectedRIRKeepsIt() {
    var s = Session(routineTitle: "A", startedAt: t0)
    log(&s, kg: 100, reps: 12, planned: PlannedSet(weightKg: 100, reps: 12))
    s.setRIR(2, slot: "a/x", index: 0)
    let rev = s.rev
    s.setRIR(2, slot: "a/x", index: 0)
    #expect(s.sets(forSlot: "a/x")[0].rir == 2 && s.rev == rev)
    s.setRIR(1, slot: "a/x", index: 0)
    #expect(s.sets(forSlot: "a/x")[0].rir == 1)
    s.setRIR(nil, slot: "a/x", index: 0) // "Quitar" is its own action
    #expect(s.sets(forSlot: "a/x")[0].rir == nil)
}

// MARK: Must-fix 7 — a new plan waits for the session to end

@Test func planSwapWaitsWhileASessionIsOpen() {
    let a = Plan(routines: [:], slots: [:])
    let b = Plan(routines: ["x": .init(title: "X", slots: [])], slots: [:])
    var inbox = PlanInbox(plan: a)
    inbox.receive(b, sessionOpen: true)
    #expect(inbox.plan == a && inbox.waiting == b)
    inbox.sessionEnded()
    #expect(inbox.plan == b && inbox.waiting == nil)
    inbox.receive(a, sessionOpen: false)
    #expect(inbox.plan == a)
    inbox.sessionEnded() // nothing waiting: no change
    #expect(inbox.plan == a)
}

// MARK: Must-fix 9 — idle prompt and auto-end

@Test func idlePromptAt20AndAutoEndAt45Minutes() {
    #expect(Idle.state(lastActivity: t0, now: t0.addingTimeInterval(19 * 60)) == .active)
    #expect(Idle.state(lastActivity: t0, now: t0.addingTimeInterval(20 * 60)) == .ask)
    #expect(Idle.state(lastActivity: t0, now: t0.addingTimeInterval(44 * 60)) == .ask)
    #expect(Idle.state(lastActivity: t0, now: t0.addingTimeInterval(45 * 60)) == .autoEnd)
    #expect(Idle.state(lastActivity: t0, now: t0.addingTimeInterval(20 * 3600)) == .autoEnd) // overnight
}

// MARK: Must-fix 1 + 4 — lockout windows and the rest Crown floor

@Test func touchAndCrownLockoutAfterAFlip() {
    var l = Lockout()
    #expect(l.allowsTouch(at: t0) && l.allowsCrown(at: t0))
    l.flip(at: t0)
    #expect(!l.allowsTouch(at: t0.addingTimeInterval(0.5)))
    #expect(!l.allowsCrown(at: t0.addingTimeInterval(0.5)))
    #expect(l.allowsCrown(at: t0.addingTimeInterval(0.6)))
    #expect(!l.allowsTouch(at: t0.addingTimeInterval(0.9)))
    #expect(l.allowsTouch(at: t0.addingTimeInterval(1.0)))
}

@Test func restCrownCantEndTheRest() {
    let end = t0.addingTimeInterval(60)
    let up = Rest.adjusted(end: end, by: 15, now: t0)
    #expect(up.end == t0.addingTimeInterval(75) && up.applied == 15)
    let down = Rest.adjusted(end: end, by: -75, now: t0)
    #expect(down.end == t0.addingTimeInterval(5) && down.applied == -55) // chip shows what really changed
    let near = Rest.adjusted(end: t0.addingTimeInterval(3), by: -15, now: t0)
    #expect(near.end == t0.addingTimeInterval(3) && near.applied == 0)
}

// MARK: L8 refinement — un-log a set and undo it

@Test func unlogThenUndoRestoresTheSetExactly() {
    var s = Session(routineTitle: "A", startedAt: t0)
    let p = PlannedSet(weightKg: 100, reps: 12)
    log(&s, kg: 100, reps: 12, planned: p)
    s.confirm(slot: "a/x", templateId: "T", title: "X", planned: p, weightKg: 102.5, reps: 11, at: t0.addingTimeInterval(90))
    s.setRIR(1, slot: "a/x", index: 1)
    let before = s
    let u = s.unlog(slot: "a/x", index: 1)
    #expect(s.sets(forSlot: "a/x").count == 1 && s.rev == before.rev + 1)
    s.restore(u!)
    #expect(s.exercises == before.exercises) // same kg, reps, rir, type, unedited, done_at, index
    #expect(s.rev == before.rev + 2)
}

@Test func unlogMiddleSetReindexesAndUndoPutsItBack() {
    var s = Session(routineTitle: "A", startedAt: t0)
    let p = PlannedSet(weightKg: 100, reps: 12)
    for r in [12, 11, 10] { log(&s, kg: 100, reps: r, planned: p) }
    let before = s.exercises
    let u = s.unlog(slot: "a/x", index: 0)!
    #expect(s.sets(forSlot: "a/x").map(\.index) == [0, 1])
    #expect(s.sets(forSlot: "a/x").map(\.reps) == [11, 10])
    s.restore(u)
    #expect(s.exercises == before)
}

@Test func undoOfTheOnlySetRecreatesTheExerciseInPlace() {
    var s = Session(routineTitle: "A", startedAt: t0)
    log(&s, kg: 100, reps: 12, planned: PlannedSet(weightKg: 100, reps: 12))
    s.confirm(slot: "a/y", templateId: "U", title: "Y", planned: PlannedSet(weightKg: nil, reps: nil),
              weightKg: 20, reps: 10, at: t0)
    let before = s.exercises
    let u = s.unlog(slot: "a/x", index: 0)!
    #expect(s.exercises.map(\.slot) == ["a/y"])
    s.restore(u)
    #expect(s.exercises == before)
    let none = s.unlog(slot: "a/x", index: 9)
    #expect(none == nil)
}
