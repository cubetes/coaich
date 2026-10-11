import Testing
@testable import AthleteCore

@Test func barbell100() {
    #expect(PlateMath.load(total: 100) == PlateLoad(perSide: [25, 15], remainderPerSide: 0))
}

@Test func plateOnlyMachine() {
    #expect(PlateMath.load(total: 60, startWeight: 0) == PlateLoad(perSide: [25, 5], remainderPerSide: 0))
}

@Test func smallestStep() {
    #expect(PlateMath.load(total: 22.5).perSide == [1.25])
}

@Test func unmatchedRemainder() {
    #expect(PlateMath.load(total: 21).remainderPerSide == 0.5)
}

@Test func belowBar() {
    #expect(PlateMath.load(total: 15) == PlateLoad(perSide: [], remainderPerSide: 0))
}

@Test func keypadParsing() {
    #expect(keypadValue("62,5") == 62.5)
    #expect(keypadValue("100") == 100)
    #expect(keypadValue("") == nil)
    #expect(keypadValue("1,2,3") == nil)
    #expect(keypadValue(",5") == 0.5)
}
