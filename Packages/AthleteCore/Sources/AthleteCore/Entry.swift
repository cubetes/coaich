import Foundation

/// Bounds and steps for what the athlete can enter on the Watch (Crown, keypad, edits).
public enum Entry {
    public static let kg: ClosedRange<Double> = 0...600
    public static let reps: ClosedRange<Int> = 1...100

    /// kg per Crown notch (G6, supersedes F1/L3 for barbells): 2,5 on a barbell or any plate-loaded slot (`start_kg`,
    /// G68) — every multiple of 2,5 from the start loads with the gym's plates (1,25 per side) — and 1,25 on
    /// everything else, an unknown substitute included (pass nil for both).
    public static func kgStep(equipment: String?, startKg: Double? = nil) -> Double {
        equipment == "barbell" || startKg != nil ? 2.5 : 1.25
    }

    /// Crown notches on kg, on the equipment's step grid, clamped to the bounds. An off-grid value (typed on
    /// the keypad, G14) first moves to the nearest grid value in the turn's direction, then one step per
    /// notch — so a barbell never lands on an unloadable weight from the Crown.
    public static func step(kg: Double, by notches: Int, equipment: String?, startKg: Double? = nil) -> Double {
        guard notches != 0 else { return kg }
        let s = kgStep(equipment: equipment, startKg: startKg)
        let grid = kg / s
        let from = notches > 0 ? (grid + 1e-6).rounded(.down) : (grid - 1e-6).rounded(.up)
        return min(max((from + Double(notches)) * s, Entry.kg.lowerBound), Entry.kg.upperBound)
    }

    public static func step(reps: Int, by notches: Int) -> Int {
        min(max(reps + notches, Entry.reps.lowerBound), Entry.reps.upperBound)
    }

    /// What the keypad's OK accepts: a number inside the bounds; reps must be whole; kg free-form with up to
    /// 2 decimals for every exercise, saved exactly as typed — never rounded or snapped (G14).
    public static func keypad(_ text: String, isReps: Bool) -> Double? {
        guard let v = keypadValue(text), (text.split(whereSeparator: { $0 == "," || $0 == "." }).dropFirst().first?.count ?? 0) <= 2
        else { return nil }
        if isReps { return v == v.rounded() && reps.contains(Int(v)) ? v : nil }
        return kg.contains(v) ? v : nil
    }
}

/// Parses what the athlete typed on the Watch keypad ("62,5" or "62.5"). `nil` when it isn't a number.
public func keypadValue(_ text: String) -> Double? {
    let t = text.replacingOccurrences(of: ",", with: ".")
    guard !t.isEmpty, t.filter({ $0 == "." }).count <= 1, let v = Double(t), v >= 0 else { return nil }
    return v
}

/// Back/forward between the sets of the slot on the Set page (decision L8).
///
/// Rule: `editing == nil` is the live position — the set to do now, or the "Completado" page when the slot
/// is done. Back walks through the logged sets (each shows "Registrada ✓"; kg/reps/type edits save at once);
/// forward walks back toward the live position and stops there. Upcoming planned sets are never shown as
/// their own page (the ladder line already shows the next one), so the only set Hecho can log is the live one.
///
/// Never left on a past set (red team N1/N2): the Watch resets to the live set on wrist-down and when the app
/// leaves the foreground — no timer (G21 removed N1's 6 s return).
///
/// The Crown edits kg/reps only once armed by a tap on a value box — live set included (scope Q10 "tap one and
/// turn the Crown"; audit 2026-10-08 #3: unarmed ghost turns added 4 notches to a live set). Hecho, a rest
/// start/end, a page change, a move to another set and wrist-down disarm it.
public struct SetNavigator: Equatable, Sendable {
    /// Index of the confirmed set being edited; `nil` = live position.
    public private(set) var editing: Int?
    /// A value box was tapped on the set on screen, so the Crown may change it.
    public private(set) var armed = false

    public init() {}

    public func canGoBack(confirmed: Int) -> Bool { (editing ?? confirmed) > 0 }
    public var canGoForward: Bool { editing != nil }
    /// Hecho and Double Tap act only on the live set, never on a set being edited.
    public var isLive: Bool { editing == nil }
    /// Whether a Crown turn changes the set on screen: only once a value box was tapped (live or past set).
    public var crownEdits: Bool { armed }

    public mutating func back(confirmed: Int) {
        guard canGoBack(confirmed: confirmed) else { return }
        editing = (editing ?? confirmed) - 1
        armed = false
    }

    public mutating func forward(confirmed: Int) {
        guard let e = editing else { return }
        editing = e + 1 < confirmed ? e + 1 : nil
        armed = false
    }

    /// A value box tapped: the Crown may now edit the set on screen.
    public mutating func arm() { armed = true }

    /// Hecho, rest start/end, page change: the Crown stops editing; the set on screen stays.
    public mutating func disarm() { armed = false }

    /// After a confirm, an un-log, a slot change, wrist-down or the app leaving the foreground: the live set.
    public mutating func reset() {
        editing = nil
        armed = false
    }
}

/// Un-logging a set (owner decision 2026-10-08): hold "Registrada ✓" for 1 s; a plain tap does nothing.
/// Double Tap never un-logs. A 4 s "Deshacer" follows.
public enum Unlog {
    public static let hold: TimeInterval = 1.0
    public static func triggers(heldFor seconds: TimeInterval) -> Bool { seconds >= hold }
}

/// The set just un-logged, offered back as "Deshacer" for 4 s — only on its own exercise. Picking another
/// exercise drops it, so "Deshacer" never shows on (or restores into) a slot out of sight (N8).
public struct PendingUndo: Equatable, Sendable {
    public private(set) var item: Session.Unlogged?

    public init() {}

    public mutating func set(_ u: Session.Unlogged?) { item = u }
    public mutating func clear() { item = nil }

    /// Another exercise became current: the undo belongs to the old one, so it goes.
    public mutating func slotChanged(to slot: String?) {
        if item?.exercise.slot != slot { item = nil }
    }
}

/// When Double Tap may log the live set (Hecho): the Set page in front, not resting, nothing over it (keypad,
/// set menu, Cambiar, "¿Has terminado?" or any other alert/dialog, N5), the flip lockout over, and not on an
/// exercise the Watch proposed until the athlete has touched it (N3, RT-04). On a past set Hecho isn't shown.
public enum DoubleTap {
    public static func logsSet(front: Bool, resting: Bool, covered: Bool, touchOK: Bool, proposed: Bool) -> Bool {
        front && !resting && !covered && touchOK && !proposed
    }
}

/// The live set's kg × reps × type on the Watch, kept across wrist-down, page swipes and sheets. It reloads
/// from the pre-fill when the set it belongs to changes (slot, exercise in use after a swap, logged-set count,
/// "+1 serie"). When only the carried-forward kg changes — a past set's weight was corrected (N6) — an untouched kg
/// follows it. `kg` nil = nothing to pre-fill (a substitute's first set, G69; a slot with no target): the Watch shows
/// an empty box and refuses Hecho until a kg is set — never a guessed or 0 kg (ADR 0001).
public struct Draft: Equatable, Sendable {
    public var kg: Double?
    public var reps = Entry.reps.lowerBound
    public var type = Session.SetType.normal
    private var key = ""
    private var loadedKg: Double?

    public init() {}

    /// `confirmed`: the slot's logged sets, warm-ups included (a warm-up typed on the set menu and logged reloads the
    /// draft, so the next set is Normal again; the G67 guide logs nothing); `template`: the exercise in use
    /// (`currentExercise(forSlot:)`), so a swap or "Volver a" reloads it.
    public mutating func sync(slot: String?, template: String? = nil, confirmed: Int, added: Int, prefill: PlannedSet?) {
        let k = "\(slot ?? "")/\(template ?? "")/\(confirmed)/\(added)"
        let pkg = prefill?.weightKg.map { min(max($0, Entry.kg.lowerBound), Entry.kg.upperBound) }
        if k != key {
            key = k
            kg = pkg
            loadedKg = pkg
            reps = min(max(prefill?.reps ?? Entry.reps.lowerBound, Entry.reps.lowerBound), Entry.reps.upperBound)
            type = .normal
        } else if pkg != loadedKg {
            if kg == loadedKg { kg = pkg }
            loadedKg = pkg
        }
    }
}

/// When a Crown edit reaches disk and the phone (G25). A Crown detent never writes or sends: the live set's
/// draft stays in memory until Hecho (which saves), and a Crown edit to a logged set waits here until the Crown
/// settles (or the Watch leaves the front), then the whole session is saved once. A per-detent JSON encode,
/// atomic file write and WatchConnectivity transfer on the main thread made every notch late.
public struct PendingSave: Equatable, Sendable {
    public private(set) var waiting = false

    public init() {}

    /// A Crown detent changed a logged set in memory.
    public mutating func crownEdit() { waiting = true }

    /// The Crown settled or the app leaves the front: true once if a Crown edit still needs saving.
    public mutating func take() -> Bool {
        defer { waiting = false }
        return waiting
    }

    /// The session was just saved for another reason: nothing waits any more.
    public mutating func saved() { waiting = false }
}

/// Inputs ignored right after the Set page flips between set and rest (red team RT-01/02/09, motion J6).
public struct Lockout: Equatable, Sendable {
    public static let touch: TimeInterval = 1.0
    public static let crown: TimeInterval = 0.6

    public private(set) var touchUntil = Date.distantPast
    public private(set) var crownUntil = Date.distantPast

    public init() {}

    /// Set ↔ rest flip, or a jump to the Set page from another page.
    public mutating func flip(at t: Date) {
        touchUntil = t.addingTimeInterval(Self.touch)
        crownUntil = t.addingTimeInterval(Self.crown)
    }

    public func allowsTouch(at t: Date) -> Bool { t >= touchUntil }
    public func allowsCrown(at t: Date) -> Bool { t >= crownUntil }
}

/// The rest countdown's end after a Crown notch or a ±15 tap. Turning down can't end the rest: it stops
/// 5 s before now (Saltar is the way to end a rest). Returns the seconds actually applied, for the chip.
public enum Rest {
    public static let floor: TimeInterval = 5

    public static func adjusted(end: Date, by seconds: TimeInterval, now: Date) -> (end: Date, applied: TimeInterval) {
        let target = end.addingTimeInterval(seconds)
        let lowest = min(end, now.addingTimeInterval(floor)) // never push an already-near end later by clamping
        let newEnd = max(target, lowest)
        return (newEnd, newEnd.timeIntervalSince(end))
    }
}

/// A forgotten session (scope Q21): ask "¿Has terminado?" after 20 min with nothing logged, finish on its
/// own after 45 min. Auto-end finishes (never discards) and stamps the last set's time.
public enum Idle: Equatable, Sendable {
    case active, ask, autoEnd

    public static let askAfter: TimeInterval = 20 * 60
    public static let endAfter: TimeInterval = 45 * 60

    public static func state(lastActivity: Date, now: Date) -> Idle {
        let idle = now.timeIntervalSince(lastActivity)
        return idle >= endAfter ? .autoEnd : idle >= askAfter ? .ask : .active
    }
}

/// The plan the Watch runs. A plan that arrives while a session is open waits until it ends, so targets,
/// set counts and slot keys never change under the athlete (red team RT-18). With no plan yet (relaunch
/// mid-session) the first one is taken at once, or nothing could be logged (N4).
public struct PlanInbox: Equatable, Sendable {
    public private(set) var plan: Plan?
    public private(set) var waiting: Plan?

    public init(plan: Plan? = nil) { self.plan = plan }

    public mutating func receive(_ new: Plan, sessionOpen: Bool) {
        if plan == nil || !sessionOpen { plan = new; waiting = nil } else { waiting = new }
    }

    public mutating func sessionEnded() {
        if let waiting { plan = waiting }
        waiting = nil
    }
}
