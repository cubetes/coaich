import Foundation
import Testing
@testable import AthleteCore

// v0.7.3 iPhone lane (G107 link): the Watch link is judged by evidence, `isWatchAppInstalled` is only a hint.

@Test func heardFromTheWatchRecentlyCountsAsConnectedEvenWhenIOSSaysTheAppIsMissing() {
    #expect(Lift.WatchLink(activated: true, paired: true, appInstalled: false, reachable: false, heardAgo: 60) == .ready)
    #expect(Lift.WatchLink(activated: true, paired: true, appInstalled: false, reachable: false,
                           heardAgo: Lift.WatchLink.heardRecently - 1) == .ready)
}

@Test func flagFalseAndNothingHeardKeepsTheAppMissingState() {
    #expect(Lift.WatchLink(activated: true, paired: true, appInstalled: false, reachable: false, heardAgo: nil) == .appMissing)
    #expect(Lift.WatchLink(activated: true, paired: true, appInstalled: false, reachable: false) == .appMissing)
}

@Test func evidenceOlderThanTheWindowNoLongerCounts() {
    #expect(Lift.WatchLink(activated: true, paired: true, appInstalled: false, reachable: false,
                           heardAgo: Lift.WatchLink.heardRecently) == .appMissing)
}

@Test func heardButNotActivatedStillSaysNotActivated() { // nothing can be sent until WatchConnectivity activates
    #expect(Lift.WatchLink(activated: false, paired: false, appInstalled: false, reachable: false, heardAgo: 5) == .notActivated)
}

@Test func reachableStillWinsWithoutEvidence() {
    #expect(Lift.WatchLink(activated: true, paired: true, appInstalled: false, reachable: true, heardAgo: nil) == .ready)
}
