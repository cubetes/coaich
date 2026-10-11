import Foundation
import Testing
@testable import AthleteCore

// v0.3.4: home/gym test 2 — no timed return from a past set (G21). (The G18 Crown gate went in v0.3.5.)

private let t0 = Date(timeIntervalSince1970: 1_791_429_164)

// MARK: G21 — a past set stays until wrist-down / background (no 6 s timer)

@Test func pastSetStaysUntilReset() {
    var nav = SetNavigator()
    nav.back(confirmed: 2)
    nav.arm()
    #expect(nav.editing == 1 && nav.crownEdits) // however long it sits there
    nav.reset() // wrist down or the app leaving the foreground
    #expect(nav.isLive)
}
