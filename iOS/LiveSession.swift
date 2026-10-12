import ActivityKit
import Foundation
import HealthKit
import WatchConnectivity
import AthleteCore

/// The Watch's live workout, mirrored to the phone (G15): AirPods cues, the lock-screen Live Activity and
/// Home's "Sesión en curso". Also starts a routine on the Watch from the phone (Q14).
@Observable
final class LiveSession: NSObject {
    let store = HKHealthStore()
    /// The latest live state while a mirrored session runs; nil otherwise.
    private(set) var state: LiveState?
    var status = ""
    /// `status` is a success ("Empezado en el reloj ✓", green), not an error (red).
    private(set) var statusOK = false
    @ObservationIgnored private var mirrored: HKWorkoutSession?
    @ObservationIgnored private var cues: [Task<Void, Never>] = []
    /// Panel updates and ends run one after another in arrival order, so the latest state always lands last (LA-02).
    @ObservationIgnored private var panelQueue: Task<Void, Never>?
    /// Observable itself: Home shows its "Diagnóstico de sonidos".
    @ObservationIgnored let player = CuePlayer()
    /// The workout's audio couldn't start (iOS refuses from the background, G50); cleared once the app opens (G53).
    @ObservationIgnored private var audioRefused = false
    /// When the current `state` arrived: a hint-only panel update keeps the Watch's real "last data" time; Entreno's
    /// hero goes stale from it like the panel (EN-05).
    private(set) var received = Date.now
    /// The app just opened without a mirrored session and asked the Watch to re-link (G59): the start button waits
    /// until the Watch had time to answer, so it never offers a start while a session may be running (EN-06).
    private(set) var linking = false
    /// A start from the phone is waiting for the Watch's answer (G100 a): the button says so and can't be tapped twice.
    private(set) var starting = false
    /// When the Watch last mirrored a session or sent its live state (G107): evidence for `PhoneModel.heardFromWatch`.
    private(set) var heardAt: Date?

    override init() {
        super.init()
        // Set at launch: iOS launches the app in the background when the Watch starts mirroring.
        store.workoutSessionMirroringStartHandler = { [weak self] session in
            session.delegate = self
            Task { @MainActor in self?.begin(session) }
        }
    }

    func requestAuthorization() async {
        try? await store.requestAuthorization(toShare: [HKObjectType.workoutType()],
                                              read: [HKObjectType.workoutType(), HKQuantityType(.heartRate)])
    }

    private func begin(_ session: HKWorkoutSession) {
        stopCues()
        mirrored = session
        state = nil
        heardAt = .now
        // Audio must start while allowed and stay on (G50): works in the foreground; from the background launch it
        // may be refused (logged), and the next `appBecameActive` tries again.
        audioRefused = !player.startWorkout("inicio")
        // G108: the background launch's one-time Live Activity grant may be gone by the Watch's first live state
        // (sent after its 3-2-1), so the panel starts now with a placeholder that state then replaces.
        panel(LiveState(routineTitle: "Entreno", startedAt: session.startDate ?? .now))
    }

    /// G53: the panel says "Abre la app para los sonidos" while cues are on and the audio couldn't start.
    private var soundOff: Bool { audioRefused && UserDefaults.standard.object(forKey: "cuesOn") as? Bool ?? true }

    private func apply(_ new: LiveState) {
        heardAt = .now
        let next = Cues.schedule(new, after: state, now: .now)
        stopCues()
        cues = next.map { cue in Task { await player.play(cue) } }
        if new.ended { return finish() }
        state = new
        received = .now
        panel(new)
    }

    /// Starts the lock-screen panel, or updates it. Queued, so a panel started right after an orphan's end (app
    /// opened, then the Watch re-mirrors, G59) is never ended by it. From the background a start works only during
    /// the mirroring launch's one-time grant (HKHealthStore.h); if refused, the next `appBecameActive` starts it.
    /// The panel's glow follows the app theme (G35/G43), read when it starts.
    /// A start's outcome (or iOS's reason for refusing) goes to "Diagnóstico" (G108).
    private func panel(_ state: LiveState, now: Date = .now) {
        serial { [soundOff, player] in
            if let outcome = await Self.show(state, soundOff: soundOff, now: now) { await player.notePanel(outcome) }
        }
    }

    /// Returns the start's outcome; nil for an update.
    private nonisolated static func show(_ state: LiveState, soundOff: Bool, now: Date) async -> String? {
        guard Activity<WorkoutAttributes>.activities.isEmpty else {
            await update(state, soundOff: soundOff, now: now)
            return nil
        }
        let theme = AppTheme(rawValue: UserDefaults.standard.string(forKey: "theme") ?? "") ?? .magenta
        do {
            _ = try Activity.request(attributes: WorkoutAttributes(theme: theme), content: content(state, soundOff: soundOff, now: now))
            return "iniciado"
        } catch {
            let e = error as NSError
            return "rechazado · \(e.domain) \(e.code) · \(error.localizedDescription)"
        }
    }

    func appBecameActive() {
        let hinted = soundOff
        if mirrored != nil { audioRefused = !player.startWorkout("app abierta") }
        if let state, !Activity<WorkoutAttributes>.activities.isEmpty {
            if soundOff != hinted { serial { [soundOff, received] in await Self.update(state, soundOff: soundOff, now: received) } } // drop the hint now
        } else if let state {
            panel(state, now: received)
        } else if mirrored == nil { serial { await Self.end(nil) } } // orphan of a killed run
        if mirrored == nil { askWatchToMirror() }
    }

    /// G59: iOS never relaunches a force-quit app for the Watch's mirroring, so the open app asks the Watch to mirror
    /// again (it does only while a workout runs). A message when the Watch app is reachable, else a queued fallback
    /// the Watch ignores after 2 min. Waits up to 5 s for WatchConnectivity, which activates just after launch.
    private func askWatchToMirror() {
        guard !linking else { return }
        linking = true
        Task {
            defer { linking = false }
            for _ in 0..<10 where WCSession.default.activationState != .activated { try? await Task.sleep(for: .milliseconds(500)) }
            let wc = WCSession.default
            guard wc.activationState == .activated, mirrored == nil else { return }
            if wc.isReachable {
                wc.sendMessage(["phoneOpen": true], replyHandler: nil, errorHandler: { @Sendable _ in WCSession.default.transferUserInfo(["phoneOpen": Date()]) })
            } else {
                wc.transferUserInfo(["phoneOpen": Date()])
            }
            // lean: a fixed 5 s for the Watch to re-mirror a running session; a reply from the Watch would be exact.
            for _ in 0..<10 where mirrored == nil { try? await Task.sleep(for: .milliseconds(500)) }
        }
    }

    /// Ends the panel and the cues. `session`: only if that session is still the current one (not an old one's late callback).
    private func finish(_ session: ObjectIdentifier? = nil) {
        if let session, session != mirrored.map(ObjectIdentifier.init) { return }
        stopCues()
        if mirrored != nil { player.endWorkout() }
        mirrored = nil
        audioRefused = false
        serial { [state] in await Self.end(state) }
        state = nil
    }

    private func serial(_ work: @escaping @Sendable () async -> Void) {
        let previous = panelQueue
        panelQueue = Task { await previous?.value; await work() }
    }

    /// A panel the app can no longer update (app killed, mirroring lost, a lost "rest over") shows as stale after
    /// this: 30 s past a running rest's end (LA-04), else 20 min, the Watch's own "¿Has terminado?" idle rule (R11).
    private nonisolated static func content(_ state: LiveState, soundOff: Bool, now: Date = .now) -> ActivityContent<WorkoutAttributes.ContentState> {
        let stale = state.isResting(at: now) ? state.restEnd!.addingTimeInterval(30) : now.addingTimeInterval(20 * 60)
        return .init(state: .init(live: state, receivedAt: now, soundOff: soundOff ? true : nil), staleDate: stale)
    }

    // Nonisolated so the Activity values never cross actors (they aren't Sendable).
    private nonisolated static func update(_ state: LiveState, soundOff: Bool, now: Date = .now) async {
        for a in Activity<WorkoutAttributes>.activities { await a.update(content(state, soundOff: soundOff, now: now)) }
    }

    private nonisolated static func end(_ last: LiveState?) async {
        for a in Activity<WorkoutAttributes>.activities {
            await a.end(last.map { .init(state: .init(live: $0, receivedAt: .now), staleDate: nil) }, dismissalPolicy: .immediate)
        }
    }

    private func stopCues() {
        cues.forEach { $0.cancel() }
        cues = []
    }

    // MARK: Start from the phone (Q14)

    /// Tells the Watch which routine to start, then wakes its app; the Watch runs 3-2-1 once both arrive. Says
    /// "Empezado" only when the Watch's mirrored session arrives (G100 a): `startWatchApp` succeeding only means iOS
    /// passed the request on — with the free team's broken link it succeeds while nothing opens.
    func startOnWatch(_ routineKey: String) async {
        status = ""
        statusOK = false
        // Not gated on isWatchAppInstalled: it can say "not installed" for an app installed from the Mac (G44); the
        // button shows that state and still allows this retry (G100 b).
        guard WCSession.default.activationState == .activated else {
            status = Lift.WatchLink.notActivated.problem ?? ""
            return
        }
        starting = true
        defer { starting = false }
        let before = mirrored.map(ObjectIdentifier.init)
        WCSession.default.transferUserInfo(["start": routineKey, "at": Date()])
        let config = HKWorkoutConfiguration()
        config.activityType = .traditionalStrengthTraining
        config.locationType = .indoor
        do {
            try await store.startWatchApp(toHandle: config)
        } catch {
            return show(.failed(error.localizedDescription))
        }
        // The Watch mirrors as soon as it prepares the workout, during its 3-2-1 (WatchModel.prepareWorkout).
        // lean: a fixed 15 s; a WatchConnectivity reply would be faster but that link is the one that fails (G100).
        let arrived = { self.state != nil || self.mirrored.map(ObjectIdentifier.init).map { $0 != before } == true }
        for _ in 0..<30 where !arrived() { try? await Task.sleep(for: .milliseconds(500)) }
        show(arrived() ? .confirmed : .noReply)
        guard statusOK else { return }
        try? await Task.sleep(for: .seconds(4))
        if statusOK { status = ""; statusOK = false }
    }

    private func show(_ reply: Lift.StartReply) {
        status = reply.text
        statusOK = reply.ok
    }
}

extension LiveSession: HKWorkoutSessionDelegate {
    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession, didChangeTo toState: HKWorkoutSessionState,
                                    from fromState: HKWorkoutSessionState, date: Date) {
        guard toState == .ended else { return }
        let id = ObjectIdentifier(workoutSession)
        Task { @MainActor in self.finish(id) }
    }

    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession, didFailWithError error: Error) {}

    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession, didReceiveDataFromRemoteWorkoutSession data: [Data]) {
        let states = data.compactMap { try? LiveState.decode($0) }
        Task { @MainActor in states.forEach { self.apply($0) } }
    }

    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession, didDisconnectFromRemoteDeviceWithError error: Error?) {
        let id = ObjectIdentifier(workoutSession)
        Task { @MainActor in self.finish(id) }
    }
}
