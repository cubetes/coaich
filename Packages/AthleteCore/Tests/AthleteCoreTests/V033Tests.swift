import Foundation
import Testing
@testable import AthleteCore

// v0.3.3: gym test 1 — Crown step per equipment on a step grid (G6) and free-form typed kg (G14).

private let t0 = Date(timeIntervalSince1970: 1_791_429_164)

private func slot(kg: Double, reps: String, equipment: String?) -> Plan.Slot {
    let eq = equipment.map { #", "equipment": "\#($0)""# } ?? ""
    let json = #"{"name": "X", "template_id": "T", "prescription": {"sets": 3}, "target": {"kg": \#(kg), "reps": "\#(reps)"}\#(eq)}"#
    return try! Plan.decoder.decode(Plan.Slot.self, from: Data(json.utf8))
}

private func loadable(_ kg: Double) -> Bool { PlateMath.unloadablePerSide(total: kg, startWeight: 20) == nil }

// MARK: G6 — step per equipment, snapping, loadability

@Test func barbellStepsTwoAndAHalfEverythingElseOneTwentyFive() {
    #expect(Entry.kgStep(equipment: "barbell") == 2.5)
    for e in ["dumbbell", "machine", "none", nil] as [String?] { #expect(Entry.kgStep(equipment: e) == 1.25) }
    #expect(Entry.step(kg: 100, by: 1, equipment: "barbell") == 102.5)
    #expect(Entry.step(kg: 100, by: -1, equipment: "barbell") == 97.5)
    #expect(Entry.step(kg: 100, by: 3, equipment: "barbell") == 107.5) // momentum: several notches at once
    #expect(Entry.step(kg: 30, by: -1, equipment: "dumbbell") == 28.75)
}

@Test func offGridValuesSnapInTheTurnsDirection() {
    #expect(Entry.step(kg: 101.25, by: -1, equipment: "barbell") == 100)  // the gym bug: down from an odd notch
    #expect(Entry.step(kg: 101.25, by: 1, equipment: "barbell") == 102.5)
    #expect(Entry.step(kg: 103.3, by: -1, equipment: "barbell") == 102.5)
    #expect(Entry.step(kg: 103.3, by: -2, equipment: "barbell") == 100)   // then one step per notch, no offset
    #expect(Entry.step(kg: 21.6, by: 1, equipment: "machine") == 22.5)
    #expect(Entry.step(kg: 21.6, by: -1, equipment: "machine") == 21.25)
    #expect(Entry.step(kg: 0.4, by: -1, equipment: "barbell") == 0)       // bounds still hold
    #expect(Entry.step(kg: 599, by: 1, equipment: "barbell") == 600)
}

@Test func theCrownNeverLandsOnAnUnloadableBarbellWeight() {
    for start in [20.0, 61.25, 100, 101.25, 103.3, 147.6] {
        var kg = start
        for _ in 0..<12 { kg = Entry.step(kg: kg, by: -1, equipment: "barbell"); if kg >= 20 { #expect(loadable(kg), "\(kg)") } }
        kg = start
        for _ in 0..<12 { kg = Entry.step(kg: kg, by: 1, equipment: "barbell"); #expect(loadable(kg), "\(kg)") }
    }
}

// MARK: G14 — the keypad saves any weight exactly

@Test func keypadKgIsFreeFormWithUpToTwoDecimals() {
    #expect(Entry.keypad("21,6", isReps: false) == 21.6)
    #expect(Entry.keypad("103,3", isReps: false) == 103.3)
    #expect(Entry.keypad("21,65", isReps: false) == 21.65)
    #expect(Entry.keypad("21,655", isReps: false) == nil)
}

@Test func typedKgIsSavedAndCarriedForwardExactly() {
    let x = slot(kg: 20, reps: "10·10·10", equipment: "machine")
    var s = Session(routineTitle: "A", startedAt: t0)
    var d = Draft()
    d.sync(slot: "a/x", confirmed: 0, added: 0, prefill: x.prefill(confirmed: [], added: 0))
    d.kg = Entry.keypad("21,6", isReps: false)!
    d.sync(slot: "a/x", confirmed: 0, added: 0, prefill: x.prefill(confirmed: [], added: 0)) // re-sync keeps it
    #expect(d.kg == 21.6)
    s.confirm(slot: "a/x", templateId: "T", title: "X", planned: x.prefill(confirmed: [], added: 0)!,
              weightKg: d.kg!, reps: d.reps, at: t0)
    #expect(s.sets(forSlot: "a/x")[0].weightKg == 21.6)
    let next = x.prefill(confirmed: s.sets(forSlot: "a/x"), added: 0)
    #expect(next?.weightKg == 21.6)
    d.sync(slot: "a/x", confirmed: 1, added: 0, prefill: next)
    #expect(d.kg == 21.6)
    let json = String(decoding: try! Session.encoder.encode(s), as: UTF8.self)
    #expect(json.contains("21.6"))
}

@Test func barbellTypedOffGridIsKeptWithAQuietHint() {
    let kg = Entry.keypad("103,3", isReps: false)!
    #expect(kg == 103.3) // never rounded or snapped
    #expect(PlateMath.unloadablePerSide(total: kg, startWeight: 20) != nil) // hint only, the value stands
}
