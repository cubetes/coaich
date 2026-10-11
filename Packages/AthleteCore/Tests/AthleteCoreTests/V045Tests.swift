import Foundation
import Testing
@testable import AthleteCore

// v0.4.5: G59 — the queued "phone app opened" fallback is ignored once it is more than 2 minutes old.

private let t0 = Date(timeIntervalSince1970: 1_791_429_164)

@Test func phoneOpenIsFreshForTwoMinutesOnly() {
    #expect(PhoneOpen.isFresh(sentAt: t0, now: t0))
    #expect(PhoneOpen.isFresh(sentAt: t0, now: t0.addingTimeInterval(120)))
    #expect(!PhoneOpen.isFresh(sentAt: t0, now: t0.addingTimeInterval(121)))       // stale queued transfer
    #expect(PhoneOpen.isFresh(sentAt: t0.addingTimeInterval(5), now: t0))           // phone clock slightly ahead
    #expect(!PhoneOpen.isFresh(sentAt: t0.addingTimeInterval(3600), now: t0))       // far-future date
}
