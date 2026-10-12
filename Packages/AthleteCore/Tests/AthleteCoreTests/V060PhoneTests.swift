import Foundation
import Testing
@testable import AthleteCore

// v0.6.0 (M3) iPhone lane: the 24 h edit's outbox (G70, red team ED-02), the edit view's grouping, "Otro" (G69).

private let t0 = Date(timeIntervalSince1970: 1_791_429_164)

/// A finished Watch session with two sets on "a/bench": rev 1 → 2 sets (3) → finish (4).
private func finished() -> Session {
    var s = Session(id: "s", routineTitle: "Push A", startedAt: t0)
    for i in 0..<2 {
        s.confirm(slot: "a/bench", templateId: "BB", title: "Press banca", planned: PlannedSet(weightKg: 100, reps: 8),
                  weightKg: 100, reps: 8, at: t0.addingTimeInterval(Double(i) * 180))
    }
    s.finish(at: t0.addingTimeInterval(3600))
    return s
}

private func edited(_ s: Session) -> Session {
    var e = s
    e.editSet(slot: "a/bench", index: 1, weightKg: 100, reps: 6, type: .normal)
    return e
}

// MARK: Phone edit = one rev

@Test func phoneEditIsOneRevAboveTheHeldOne() {
    var box = Outbox()
    let w = finished()
    box.receive(w, final: true)
    box.markSent(id: "s", rev: w.rev)
    var e = edited(w)
    e.setRIR(2, slot: "a/bench", index: 0) // several changes, still one rev
    let saved = box.save(edit: e)
    #expect(saved?.rev == w.rev + 1)
    #expect(box.pending.map(\.rev) == [w.rev + 1])
    #expect(saved?.exercises[0].sets[1].reps == 6 && saved?.exercises[0].sets[1].unedited == false)
    #expect(saved?.exercises[0].sets[0].unedited == true) // RIR only: still as shown (ED-07)
    let r1 = box.save(edit: saved!)
    #expect(r1 == nil) // nothing changed: no rev
}

@Test func phoneNeverEditsASessionInProgressOrItsNote() {
    var box = Outbox()
    var live = Session(id: "s", routineTitle: "Push A", startedAt: t0)
    live.confirm(slot: "a/x", templateId: "X", title: "X", planned: PlannedSet(weightKg: 10, reps: 5), weightKg: 10,
                 reps: 5, at: t0)
    box.receive(live)
    var e = live
    e.editSet(slot: "a/x", index: 0, weightKg: 12, reps: 5, type: .normal)
    let r2 = box.save(edit: e)
    #expect(r2 == nil) // ED-01
    var w = finished()
    w.setNote("Bien")
    box.receive(w, final: true)
    var f = edited(w)
    #expect(box.save(edit: f)?.note == "Bien") // the Watch's note rides along untouched (G78 lets the phone change it)
}

// MARK: Note merge (red team must-fix 4 / ED-02)

@Test func lateWatchNoteWithTheSameRevMergesIntoThePhoneEdit() {
    var box = Outbox()
    let w = finished()
    box.receive(w)
    let phone = box.save(edit: edited(w))!            // rev N+1
    var note = w
    note.setNote("Hombro raro")                         // the Watch's stale copy: also N+1
    #expect(note.rev == phone.rev)
    let r3 = box.receive(note)
    #expect(r3)
    let held = box.items["s"]!.session
    #expect(held.note == "Hombro raro")
    #expect(held.exercises == phone.exercises)          // the phone's fix kept
    #expect(held.rev == phone.rev + 1)                  // above both: the Worker takes it, the Watch's ack ≥ its rev
    #expect(box.pending.map(\.rev) == [held.rev])
    let r4 = box.receive(note)
    #expect(!r4)                         // a replay of the same Watch rev changes nothing
    #expect(box.items["s"]!.session.rev == held.rev)
}

@Test func watchNoteAboveThePhoneRevStillOnlyBringsTheNote() {
    var box = Outbox()
    let w = finished()
    box.receive(w)
    let phone = box.save(edit: edited(w))!
    var note = w
    note.setNote("uno")
    note.setNote("dos")                                 // N+2 > the phone's N+1, built on the stale sets
    let r5 = box.receive(note)
    #expect(r5)
    let held = box.items["s"]!.session
    #expect(held.note == "dos" && held.exercises == phone.exercises && held.rev == note.rev + 1)
}

@Test func phoneEditAfterTheWatchNoteKeepsTheNote() {
    var box = Outbox()
    var w = finished()
    w.setNote("Bien")
    box.receive(w, final: true)
    let saved = box.save(edit: edited(w))!
    #expect(saved.note == "Bien" && saved.rev == w.rev + 1)
    let r6 = box.receive(w)
    #expect(!r6) // the Watch re-sends its final rev: replay, nothing changes
    #expect(box.items["s"]!.session == saved)
}

@Test func watchRevsBeforeAnyPhoneEditStayPlainUpdates() {
    var box = Outbox()
    var w = finished()
    box.receive(w)
    w.setNote("ok")
    let r7 = box.receive(w)
    #expect(r7)
    #expect(box.items["s"]!.session == w)
}

@Test func outboxSavedBefore060StillLoadsAndReplaysAreIgnored() throws {
    let w = finished()
    let old = #"{"items": {"s": {"session": \#(String(decoding: try Session.encoder.encode(w), as: UTF8.self)), "sent_rev": 4}}}"#
    var box = try Session.decoder.decode(Outbox.self, from: Data(old.utf8))
    let r8 = box.receive(w)
    #expect(!r8)
    #expect(!box.canEdit(id: "s", now: t0.addingTimeInterval(3700))) // no final rev seen yet
    let r9 = box.receive(w, final: true)
    #expect(r9)                             // the final flag alone is news
    #expect(box.canEdit(id: "s", now: t0.addingTimeInterval(3700)))
}

// MARK: Edit window on the phone (G70: final rev + 24 h after the end)

@Test func editUnlocksOnTheFinalRevAndLocksAfter24h() {
    var box = Outbox()
    let w = finished()
    let end = w.endedAt!
    box.receive(w)
    #expect(!box.canEdit(id: "s", now: end))            // "Esperando al reloj…"
    box.receive(w, final: true)
    #expect(box.canEdit(id: "s", now: end.addingTimeInterval(24 * 3600)))
    #expect(!box.canEdit(id: "s", now: end.addingTimeInterval(24 * 3600 + 1)))
    #expect(!box.canEdit(id: "nope", now: end))
}

// MARK: Edit view grouping

@Test func slotGroupsKeepSwapsTogetherWithSlotLevelOffsets() {
    var s = Session(id: "g", routineTitle: "Push A", startedAt: t0)
    let p = PlannedSet(weightKg: 100, reps: 8)
    s.confirm(slot: "a/bench", templateId: "BB", title: "Banca", planned: p, weightKg: 100, reps: 8, at: t0)
    s.confirm(slot: "a/fly", templateId: "FL", title: "Aperturas", planned: p, weightKg: 20, reps: 12, at: t0)
    s.substitute(slot: "a/bench", templateId: "DB", title: "Banca mancuernas", planned: "BB")
    s.confirm(slot: "a/bench", templateId: "BB", title: "Banca", planned: p, weightKg: 36, reps: 8, at: t0)
    #expect(s.slotGroups == [
        .init(slot: "a/bench", entries: [.init(position: 0, offset: 0), .init(position: 2, offset: 1)]),
        .init(slot: "a/fly", entries: [.init(position: 1, offset: 0)]),
    ])
    #expect(s.sets(forSlot: "a/bench")[1].weightKg == 36) // offset 1 = the substitute's first set
}

// MARK: "Otro (en el iPhone)" list

@Test func swapChoicesPutTheCoachFirstAndListEveryPlanExerciseOnce() throws {
    let json = #"""
    {"routines": {"a": {"title": "Push A", "slots": ["a/bench", "a/fly"]}},
     "slots": {
      "a/bench": {"name": "Press de banca con barra", "template_id": "BB", "prescription": {"sets": 3},
                  "alternatives": [{"template_id": "DB", "name": "Press de banca con mancuernas"}]},
      "a/fly": {"name": "Aperturas", "template_id": "FL", "prescription": {"sets": 3},
                "alternatives": [{"template_id": "DB", "name": "Press de banca con mancuernas"},
                                 {"template_id": "CC", "name": "Cruce de poleas"}]},
      "b/x": {"name": "Sin plantilla", "prescription": {"sets": 3}}}}
    """#
    let plan = try Plan.decoder.decode(Plan.self, from: Data(json.utf8))
    let c = plan.swapChoices(slot: "a/bench")
    #expect(c.coach.map(\.templateId) == ["DB"])
    #expect(c.plan.map(\.name) == ["Aperturas", "Cruce de poleas", "Press de banca con barra"]) // DB not twice
    #expect(plan.swapChoices(slot: "zz").coach.isEmpty)
}

// MARK: Re-check v0.6.0 (RC-02): the phone's kg/reps fields write every keystroke

@Test func retypingTheSameNumberKeepsUnedited() {
    var box = Outbox()
    let w = finished()
    box.receive(w, final: true)
    var e = w
    e.editSet(slot: "a/bench", index: 0, weightKg: 10, reps: 8, type: .normal)  // "100" → "10" while typing
    e.editSet(slot: "a/bench", index: 0, weightKg: 100, reps: 8, type: .normal) // → "100" again
    #expect(e.exercises[0].sets[0].unedited == false)
    #expect(box.save(edit: e) == nil) // back where it was: no rev, `unedited` as the Watch sent it
    e.editSet(slot: "a/bench", index: 1, weightKg: 100, reps: 6, type: .normal)
    e.addSet(exercise: 0, weightKg: 100, reps: 8, at: w.exercises[0].sets[0].doneAt) // a copy with the same done_at
    let saved = box.save(edit: e)
    #expect(saved?.exercises[0].sets.map(\.unedited) == [true, false, false]) // the real change and the added set only
}
