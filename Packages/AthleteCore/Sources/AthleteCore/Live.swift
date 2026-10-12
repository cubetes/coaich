import Foundation

/// What the Watch tells the phone over the mirrored workout (G15): enough for the AirPods cues and the
/// lock-screen panel. Sent whole on every change; the phone times the cues itself from these dates, so a
/// late message never makes a countdown late.
public struct LiveState: Codable, Sendable, Hashable { // Hashable: it is the Live Activity's ContentState
    public var routineTitle: String
    /// Session start (elapsed time). During the 3-2-1 countdown it is the coming "¡Vamos!" moment.
    public var startedAt: Date
    /// "¡Vamos!" moment while the start countdown runs; nil once the session is running.
    public var go: Date?
    /// Exercise on the Set page (Spanish name) and its working-set number / planned count.
    public var exercise: String?
    public var setNumber: Int?
    public var setsPlanned: Int?
    /// Rest running until this moment; nil when no rest runs.
    public var restEnd: Date?
    /// Confirmed sets in the session; a rise is the "set saved" cue.
    public var setsLogged: Int
    /// The session finished or was discarded: the phone ends the panel and stops cueing.
    public var ended: Bool
    /// When the running rest began (the bar and ring drain from here, G32).
    public var restStart: Date?
    /// What the Watch would log now: the live set's kg × reps (G32 "Obj", G36 "Siguiente"). Sent on state
    /// changes and once when the Crown settles, never per notch (G25).
    public var targetKg: Double?
    public var targetReps: Int?
    /// The live set is a warm-up ("Calent." / "CAL"; `setNumber` is nil then).
    public var warmup: Bool?
    /// Workout bar (G33): planned/done working sets per exercise in routine order (`Plan.segments`: "+1 serie" counts
    /// since v0.6.2), and which one is on screen.
    public var segments: [Segment]?
    public var current: Int?
    /// The routine and the workout bar's slot keys, in `segments` order (red team EN-18): the phone marks its rows by
    /// key, never by index against a plan that may differ. Absent from Watch builds before 0.7.1.
    public var routineKey: String?
    public var slots: [String]?

    public struct Segment: Codable, Sendable, Hashable {
        public var planned: Int
        public var done: Int
        public init(planned: Int, done: Int) { self.planned = planned; self.done = done }
    }

    public init(routineTitle: String, startedAt: Date, go: Date? = nil, exercise: String? = nil, setNumber: Int? = nil,
                setsPlanned: Int? = nil, restEnd: Date? = nil, setsLogged: Int = 0, ended: Bool = false,
                restStart: Date? = nil, targetKg: Double? = nil, targetReps: Int? = nil, warmup: Bool? = nil,
                segments: [Segment]? = nil, current: Int? = nil) {
        self.routineTitle = routineTitle
        self.startedAt = startedAt
        self.go = go
        self.exercise = exercise
        self.setNumber = setNumber
        self.setsPlanned = setsPlanned
        self.restEnd = restEnd
        self.setsLogged = setsLogged
        self.ended = ended
        self.restStart = restStart
        self.targetKg = targetKg
        self.targetReps = targetReps
        self.warmup = warmup
        self.segments = segments
        self.current = current
    }

    /// One rule for rest vs set everywhere on the phone (red team LA-03): a rest whose end has passed is over.
    public func isResting(at now: Date) -> Bool { restEnd.map { $0 > now } ?? false }

    /// Default JSON dates (seconds as a Double): sub-second precision, which the cue timing needs.
    public func encoded() throws -> Data { try JSONEncoder().encode(self) }
    public static func decode(_ data: Data) throws -> LiveState { try JSONDecoder().decode(LiveState.self, from: data) }
}

/// A sound the phone plays in the headphones.
public enum Cue: Equatable, Sendable {
    /// Start countdown 3 · 2 · 1, then go.
    case start(Int), go
    /// Rest countdown 5…1 (louder near 0), then rest over.
    case restTick(Int), restOver
    case setSaved
}

public struct ScheduledCue: Equatable, Sendable {
    public var at: Date
    public var cue: Cue
    public init(at: Date, cue: Cue) { self.at = at; self.cue = cue } // the phone's "Probar sonido"
}

public enum Cues {
    /// A cue more than this late is dropped, not played (it would land on the wrong second).
    public static let lateness: TimeInterval = 0.4
    /// The phone places a tone on the audio clock this long before its time; from then on it can't be cancelled.
    public static let placeAhead: TimeInterval = 0.15

    /// The cues to schedule after `new` arrives, replacing everything scheduled before — except that a rest
    /// ending on its own (the Watch clears `restEnd` at 0) keeps a "rest over" that wasn't placed yet (the phone's
    /// clock may run a little behind the Watch's) and never plays it twice. A rest cleared well before its end was skipped: nothing more plays.
    public static func schedule(_ new: LiveState, after old: LiveState?, now: Date) -> [ScheduledCue] {
        if new.ended { return [] }
        var out: [ScheduledCue] = []
        if let old, new.setsLogged > old.setsLogged { out.append(.init(at: now, cue: .setSaved)) }
        if let go = new.go {
            out += (1...3).map { ScheduledCue(at: go.addingTimeInterval(-Double($0)), cue: .start($0)) }
            out.append(.init(at: go, cue: .go))
        }
        if let end = new.restEnd {
            out += (1...5).map { ScheduledCue(at: end.addingTimeInterval(-Double($0)), cue: .restTick($0)) }
            out.append(.init(at: end, cue: .restOver))
        } else if let oldEnd = old?.restEnd, now >= oldEnd.addingTimeInterval(-1), now < oldEnd.addingTimeInterval(-placeAhead) {
            out.append(.init(at: oldEnd, cue: .restOver)) // past `placeAhead` the first one is already on the audio clock
        }
        if let oldGo = old?.go, new.go == nil, now < oldGo { out.append(.init(at: now, cue: .go)) } // countdown skipped
        return out.filter { $0.at >= now.addingTimeInterval(-lateness) }.sorted { $0.at < $1.at }
    }

    /// AirPods or wired headphones only (G15, G28): never the phone's speaker, a receiver, AirPlay, or another
    /// Bluetooth output (gym speaker, car). Outputs are (`AVAudioSession.Port` raw value, port name) so this stays
    /// testable without AVFoundation.
    public static func isHeadphones(_ outputs: [(type: String, name: String)]) -> Bool {
        let bluetooth: Set = ["BluetoothA2DPOutput", "BluetoothLE", "BluetoothHFP"]
        return !outputs.isEmpty && outputs.allSatisfy {
            $0.type == "Headphones" || (bluetooth.contains($0.type) && $0.name.localizedCaseInsensitiveContains("AirPods"))
        }
    }
}

/// Start from iPhone (G15): the phone sends the routine over WatchConnectivity and launches the Watch app with a
/// workout configuration. The countdown starts once both arrived, in any order, each less than a minute old;
/// either one alone (a late queued transfer, a stray launch) just opens the app on its routine list.
public struct PhoneStart: Sendable {
    public static let maxAge: TimeInterval = 60
    private var request: (key: String, at: Date)?
    private var launchedAt: Date?

    public init() {}

    /// The start request; `at` is when the phone sent it. Returns the routine to start now, or nil.
    public mutating func requested(_ routineKey: String, at: Date, now: Date) -> String? {
        request = (routineKey, at)
        return ready(now: now)
    }

    /// The phone launched the app with a workout configuration. Returns the routine to start now, or nil.
    public mutating func launched(now: Date) -> String? {
        launchedAt = now
        return ready(now: now)
    }

    private mutating func ready(now: Date) -> String? {
        guard let r = request, let l = launchedAt,
              now.timeIntervalSince(r.at) < Self.maxAge, now.timeIntervalSince(l) < Self.maxAge else { return nil }
        self = PhoneStart() // used once
        return r.key
    }
}

/// G59: the iPhone app opened without a mirrored workout (e.g. after a force-quit) and asks the Watch to mirror
/// again. The queued fallback can arrive late; one older than this is ignored (the app may be long closed).
public enum PhoneOpen {
    public static let maxAge: TimeInterval = 120

    public static func isFresh(sentAt: Date, now: Date) -> Bool {
        let age = now.timeIntervalSince(sentAt)
        return age >= -maxAge && age <= maxAge // clocks may differ a little; a far-future date is as suspect as an old one
    }
}

extension Plan {
    /// THE working-sets count (G79, red team MT-01), used by the workout bar (G33), Métricas, Resumen and the summary
    /// (G41): one segment per loggable slot of the routine, in routine order. `planned` = the plan's sets plus
    /// "+1 serie"; `done` = working sets logged on the slot (a swap's sets included, warm-ups never), capped at planned,
    /// so extra sets never read "19/18" (they still count in kg and reps). A slot without a template can't be logged
    /// and is left out.
    public func segments(routineKey: String, session: Session?, added: [String: Int]) -> [LiveState.Segment] {
        barSlots(routineKey).map { key in
            let planned = setCount(key, added: added)
            return LiveState.Segment(planned: planned, done: min(planned, session?.sets(forSlot: key).working.count ?? 0))
        }
    }

    public struct Progress: Equatable, Sendable {
        public let done: Int
        public let planned: Int
        public init(done: Int, planned: Int) { self.done = done; self.planned = planned }
    }

    /// "10/18 series": the segments summed.
    public func progress(routineKey: String, session: Session?, added: [String: Int]) -> Progress {
        let s = segments(routineKey: routineKey, session: session, added: added)
        return Progress(done: s.reduce(0) { $0 + $1.done }, planned: s.reduce(0) { $0 + $1.planned })
    }

    /// The slot keys behind the workout bar's segments, same order.
    func barSlots(_ routineKey: String) -> [String] {
        (routines[routineKey]?.slots ?? []).filter { slots[$0]?.templateId != nil }
    }
}

extension LiveState {
    /// The state the Watch sends (G37), from what it holds: the running session, else the 3-2-1 countdown for
    /// `routineKey` ending at `go`; nil when neither runs. When Hecho would log nothing on `slot` (after the
    /// routine's last set, or a finished exercise left open) there is no exercise, set, target or current
    /// segment: with every segment done the phone shows "Todo hecho" (LA-06).
    public static func watch(plan: Plan?, routineKey: String?, session: Session?, slot: String?, added: [String: Int],
                             draft: Draft, restStart: Date?, restEnd: Date?, go: Date?) -> LiveState? {
        guard let session else {
            guard let go, let rk = routineKey, let routine = plan?.routines[rk] else { return nil }
            var s = LiveState(routineTitle: routine.title, startedAt: go, go: go,
                              segments: plan?.segments(routineKey: rk, session: nil, added: added))
            s.routineKey = rk
            s.slots = plan?.barSlots(rk)
            return s
        }
        var s = LiveState(routineTitle: session.routineTitle, startedAt: session.startedAt,
                          restEnd: restEnd, setsLogged: session.exercises.reduce(0) { $0 + $1.sets.count },
                          ended: session.endedAt != nil,
                          restStart: restEnd == nil ? nil : restStart) // the Watch keeps restStart after a rest
        if let rk = routineKey, let plan {
            s.segments = plan.segments(routineKey: rk, session: session, added: added)
            s.routineKey = rk
            s.slots = plan.barSlots(rk)
        }
        guard let plan, let slot, let planSlot = plan.slots[slot],
              planSlot.prefill(confirmed: session.sets(forSlot: slot), added: added[slot] ?? 0) != nil else { return s }
        s.exercise = planSlot.inUse(session.currentExercise(forSlot: slot)).short // the substitute after a swap (SB-09)
        s.warmup = draft.type == .warmup
        s.setNumber = draft.type == .warmup ? nil : session.sets(forSlot: slot).working.count + 1
        s.setsPlanned = plan.setCount(slot, added: added)
        s.targetKg = draft.kg   // what Hecho would log (the Crown-edited draft once the Crown settles)
        s.targetReps = draft.reps
        s.current = routineKey.flatMap { plan.barSlots($0).firstIndex(of: slot) }
        return s
    }
}
