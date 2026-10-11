import Foundation

/// The published snapshot envelope from `GET /api/snapshot/latest`, decoded only as far as M1 needs.
/// Unknown fields are ignored; decode with `Plan.decoder` (snake_case keys).
public struct SnapshotEnvelope: Decodable, Sendable {
    public let schemaVersion: String
    public let asOfDate: String?
    public let publishedAt: String?
    public let payload: Payload

    public struct Payload: Decodable, Sendable {
        public let workout: Plan?
    }
}

/// The routines and slots of the mesocycle in force. Also the compact document the phone sends to the Watch.
public struct Plan: Codable, Sendable, Equatable {
    public var routines: [String: Routine]
    public var slots: [String: Slot]
    public var week: [WeekDay]?

    public init(routines: [String: Routine], slots: [String: Slot], week: [WeekDay]? = nil) {
        self.routines = routines
        self.slots = slots
        self.week = week
    }

    public struct Routine: Codable, Sendable, Equatable {
        public let title: String
        /// Slot keys (`routine_key/slug`) in routine order.
        public let slots: [String]
    }

    public struct WeekDay: Codable, Sendable, Equatable {
        public let date: String
        public let routineKey: String?
    }

    public struct Slot: Codable, Sendable, Equatable {
        public let name: String
        /// Hevy template ID (snapshot 1.8). Without it a slot cannot be logged.
        public let templateId: String?
        public let prescription: Prescription
        public let target: Target?
        /// Top set of recent sessions, newest first (snapshot `history`).
        public let history: [HistoryItem]?
        /// Hevy equipment word ("barbell", "dumbbell", "machine", …), snapshot 1.9. Absent in older snapshots.
        public let equipment: String?
        /// Best marks in the current series of this routine × exercise (snapshot `records`, 1.4.x). Optional.
        public let records: Records?
        /// Coach's short name for tight spaces (snapshot 1.10, ≤ the validator's max); nil in older snapshots.
        public let shortName: String?
        /// Superset group inside the routine (snapshot 1.11, G39): slots with the same value are done back to back.
        public let superset: Superset?
        /// Coach's warm-up pattern on marked slots (snapshot 1.10, Q18); nil elsewhere and in older snapshots.
        public let warmup: Warmup?
        /// The 2–3 exercises the coach allows in this slot's place (snapshot 1.10, Q22); nil in older snapshots.
        public let alternatives: [Alternative]?
        /// Where plates start on a plate-loaded slot (companion PR #13, G68): 20 for a barbell, 0 when only the
        /// plates count (hack squat, T-bar, prensa); nil = not plate-loaded, or an older snapshot. Read via `plateStart`.
        public let startKg: Double?
        /// 1 = plates on one sleeve (T-bar, landmine): the plate list is the whole load, not per side. Absent = 2.
        public let plateSides: Int?
        /// Hevy primary muscle ("chest", "lats", …; companion PR #13, G73): the iPhone "Otro" filter. nil in older snapshots.
        public let primaryMuscle: String?

        public struct Warmup: Codable, Sendable, Equatable {
            public let pattern: [Step]
            /// `pct` = share of the first working weight (0 < pct ≤ 1), `reps` 1–30 (the validator's bounds).
            public struct Step: Codable, Sendable, Equatable {
                public let pct: Double
                public let reps: Int
            }
        }

        public struct Alternative: Codable, Sendable, Equatable {
            public let templateId: String
            /// Spanish name (≤ 120 chars), what the session's `title` becomes.
            public let name: String
            /// Not written by the 1.10 validator yet; read if it ever is.
            public let shortName: String?
            /// Hevy primary muscle, like the slot's (G73).
            public let primaryMuscle: String?
        }

        /// The spec's `superset_id`, which the snapshot may write as a number or a string; kept as a string.
        public struct Superset: Codable, Sendable, Hashable, ExpressibleByStringLiteral {
            public let id: String
            public init(stringLiteral id: String) { self.id = id }
            public init(from decoder: Decoder) throws {
                let c = try decoder.singleValueContainer()
                if let n = try? c.decode(Int.self) { id = String(n) } else { id = try c.decode(String.self) }
            }
            public func encode(to encoder: Encoder) throws {
                var c = encoder.singleValueContainer()
                try c.encode(id)
            }
        }

        public struct Records: Codable, Sendable, Equatable {
            /// Best Epley e1RM over 3–12-rep sets, or nil (a high-rep slot may have none). Named `bestE1Rm`
            /// because `convertFromSnakeCase` capitalises after the digit ("best_e1rm" → "bestE1Rm").
            public let bestE1Rm: Mark?
            public struct Mark: Codable, Sendable, Equatable {
                public let kg: Double
                public let date: String?
            }
        }

        public struct HistoryItem: Codable, Sendable, Equatable {
            public let date: String?
            /// Heaviest working set, e.g. "105×10".
            public let top: String
        }

        public struct Prescription: Codable, Sendable, Equatable {
            public let sets: Int
            public let restS: Int?
        }

        public struct Target: Codable, Sendable, Equatable {
            public let kg: Double
            /// Per-set reps joined by "·", e.g. "10·10·9·8".
            public let reps: String

            public var repsList: [Int] {
                reps.split(separator: "·").compactMap { Int($0.trimmingCharacters(in: .whitespaces)) }
            }
        }
    }

    /// Local calendar day as the snapshot writes it ("2026-10-07").
    public static func day(_ date: Date = .now) -> String {
        date.formatted(Date.ISO8601FormatStyle(timeZone: .current).year().month().day())
    }

    /// Routine keys in the owner's fixed rotation (G40): Push A, Pull A, Legs A, Push B, Pull B, Legs B — by the title's
    /// last word (the variant letter), then Push < Pull < Legs, then the title. The snapshot's routines are a JSON
    /// object, whose order a decoder doesn't keep, so the order is derived from the titles.
    public var rotation: [String] {
        func rank(_ title: String) -> (String, Int, String) {
            let words = title.lowercased().split(separator: " ")
            let kind = ["push", "pull", "legs"].firstIndex(of: String(words.first ?? "")) ?? 3
            return (String(words.last ?? ""), kind, title)
        }
        return routines.keys.sorted { rank(routines[$0]!.title) < rank(routines[$1]!.title) }
    }

    public struct RoutineSuggestion: Equatable, Sendable {
        public let key: String
        /// It is today's routine in the calendar (`week`), not the rotation's next.
        public let today: Bool
        public init(key: String, today: Bool) { self.key = key; self.today = today }
    }

    /// The routine to suggest (G40): today's calendar routine when the snapshot's `week` has one and it wasn't done
    /// today; otherwise the one after the last finished session's routine in `rotation` (wrapping), or the first.
    /// `lastDay` is the local day the last session started (`Plan.day(_:)`). The iPhone uses the same rule.
    public func suggestedRoutine(lastTitle: String?, lastDay: String?, today: String = Plan.day()) -> RoutineSuggestion? {
        if let key = week?.first(where: { $0.date == today })?.routineKey, let r = routines[key],
           !(lastDay == today && lastTitle == r.title) {
            return .init(key: key, today: true)
        }
        let order = rotation
        guard !order.isEmpty else { return nil }
        let last = lastTitle.flatMap { t in order.firstIndex { routines[$0]?.title == t } }
        return .init(key: order[last.map { ($0 + 1) % order.count } ?? 0], today: false)
    }

    /// Routine keys in display order: the suggestion first, then the rotation from there.
    public func routineKeys(lastTitle: String? = nil, lastDay: String? = nil, today: String = Plan.day()) -> [String] {
        let order = rotation
        guard let key = suggestedRoutine(lastTitle: lastTitle, lastDay: lastDay, today: today)?.key,
              let i = order.firstIndex(of: key) else { return order }
        return Array(order[i...] + order[..<i])
    }

    public static var decoder: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    public static var encoder: JSONEncoder {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        return e
    }
}

/// A set as pre-filled before the athlete confirms it. `nil` means no target value to show.
public struct PlannedSet: Equatable, Sendable {
    public let weightKg: Double?
    public let reps: Int?

    public init(weightKg: Double?, reps: Int?) {
        self.weightKg = weightKg
        self.reps = reps
    }
}

extension Plan {
    /// The plate line for slot `key` (G68): where the plates start and on how many sleeves. Only from a snapshot that
    /// carries `start_kg` on some slot (1.11, companion PR #13): an older one can't say the T-bar (Hevy "barbell") is
    /// plates only on one sleeve, and a wrong plate list is worse than none (red team PL-01).
    public func plateLine(_ key: String) -> (start: Double, sides: Int)? {
        guard slots.values.contains(where: { $0.startKg != nil }), let s = slots[key], let start = s.plateStart
        else { return nil }
        return (start, s.sides)
    }
}

extension Plan.Slot {
    /// Where the plates start (G68): the coach's `start_kg`, else the 20 kg bar on a barbell slot (older snapshots);
    /// nil = no plates (a stack, dumbbells, an unknown machine). A negative `start_kg` is ignored like an absent one.
    public var plateStart: Double? { PlateMath.startWeight(equipment: equipment, startKg: startKg) }
    /// Sleeves the plates go on: 1 only when the coach says so, else 2.
    public var sides: Int { plateSides == 1 ? 1 : 2 }

    /// What is done in this slot now (G69): the plan's exercise, or the substitute after a swap with its coach short
    /// name when the alternative has one (else its full name). `name` is for VoiceOver.
    public struct InUse: Equatable, Sendable {
        public let name: String
        public let short: String
        public let substituted: Bool
        public init(name: String, short: String, substituted: Bool) {
            self.name = name; self.short = short; self.substituted = substituted
        }
    }

    /// `current` = the session's `currentExercise(forSlot:)`.
    public func inUse(_ current: Session.Exercise?) -> InUse {
        guard let c = current, c.substituted else { return InUse(name: name, short: shortName ?? name, substituted: false) }
        let alt = alternatives?.first { $0.templateId == c.exerciseTemplateId }
        return InUse(name: c.title, short: alt?.shortName ?? c.title, substituted: true)
    }

    /// One set per target rep at the target kg; with no target, `prescription.sets` empty sets.
    public var plannedSets: [PlannedSet] {
        if let target, !target.repsList.isEmpty {
            return target.repsList.map { PlannedSet(weightKg: target.kg, reps: $0) }
        }
        return Array(repeating: PlannedSet(weightKg: nil, reps: nil), count: max(0, prescription.sets))
    }
}

extension Plan.Slot {
    /// Rest after a set: the plan's `rest_s`, or 90 s when the plan has none.
    public var restSeconds: Int {
        if let r = prescription.restS, r > 0 { return r }
        return 90
    }

    /// What to pre-fill for the next set, given the sets already confirmed and the sets added with
    /// "+1 serie". Planned sets come first; each added set copies the last confirmed one.
    /// `nil` when every planned and added set is done.
    ///
    /// The kg carries forward: once a working set is confirmed, the next planned set shows that set's kg,
    /// not the target (red team RT-03: the bar still holds 102,5 after you changed it). Reps stay the plan's.
    /// With no target, kg and reps both come from the last confirmed set. Warm-ups count for nothing.
    ///
    /// After a swap (G69, red team SB-01/02) kg carries only from `exerciseSets` — the slot's sets done on the exercise
    /// in use now — never across exercises: a substitute with none has no kg (`substituted`), the plan's own exercise
    /// falls back to the target. nil `exerciseSets` = no swap: every confirmed set counts.
    public func prefill(confirmed: [Session.SetEntry], added: Int, exerciseSets: [Session.SetEntry]? = nil,
                        substituted: Bool = false) -> PlannedSet? {
        let planned = plannedSets
        let own = exerciseSets ?? confirmed
        let n = confirmed.working.count // warm-ups never use up planned sets (N7)
        if n < planned.count {
            // A drop set's stripped weight never carries (N10): the next set goes back to the last real working kg.
            let lastWork = own.last { $0.type != .warmup && $0.type != .dropset }
            return PlannedSet(weightKg: lastWork?.weightKg ?? (substituted ? nil : planned[n].weightKg),
                              reps: planned[n].reps ?? confirmed.last?.reps)
        }
        guard n < planned.count + added, let last = confirmed.last else { return nil }
        return PlannedSet(weightKg: own.last?.weightKg ?? (substituted ? nil : planned.last?.weightKg), reps: last.reps)
    }

    /// `prefill` for the slot `key` of a running session, swap-aware: kg from the exercise in use only.
    public func prefill(session: Session?, slot key: String, added: Int) -> PlannedSet? {
        let current = session?.currentExercise(forSlot: key)
        let own = current.map { c in
            session!.exercises.filter { $0.slot == key && $0.exerciseTemplateId == c.exerciseTemplateId }.flatMap(\.sets)
        }
        return prefill(confirmed: session?.sets(forSlot: key) ?? [], added: added, exerciseSets: own,
                       substituted: current?.substituted ?? false)
    }
}

extension Plan.Slot {
    /// The warm-up ramp (Q17, G67) for a first working weight (the live draft's kg). Each step's kg = pct × working,
    /// rounded to the nearest loadable weight — a tie rounds **up** (0,5 × 42,5 = 21,25 → 22,5; warm-ups count for
    /// nothing, so either way is fine; the code and DESIGN.md say up). Plate-loaded slots (`plateStart`, G68) use the
    /// 2,5 kg grid from their start (the 20 kg bar, 0 when only plates count); `startWeight` overrides it. Anything else
    /// uses `Entry.kgStep` from 0. Never below the start, never above the working weight (the step below it instead);
    /// a step that lands on the previous one's kg is dropped. Empty with no pattern, no working weight, or a working
    /// weight below the bar.
    public func warmupSets(workingKg: Double?, startWeight: Double? = nil) -> [PlannedSet] {
        guard let pattern = warmup?.pattern, let w = workingKg, w > 0 else { return [] }
        let start = startWeight ?? plateStart
        let base = start ?? 0
        let step = start == nil ? Entry.kgStep(equipment: equipment) : PlateMath.step
        func grid(_ kg: Double, _ rule: FloatingPointRoundingRule) -> Double {
            base + ((kg - base) / step + (rule == .down ? 1e-9 : 0)).rounded(rule) * step
        }
        var out: [PlannedSet] = []
        for s in pattern {
            var kg = grid(s.pct * w, .toNearestOrAwayFromZero)
            if kg > w { kg = grid(w, .down) }
            kg = max(kg, base)
            guard kg <= w, out.last?.weightKg != kg else { continue }
            out.append(PlannedSet(weightKg: kg, reps: s.reps))
        }
        return out
    }
}

extension Plan {
    /// Planned sets for a slot plus the ones added with "+1 serie".
    public func setCount(_ slotKey: String, added: [String: Int] = [:]) -> Int {
        (slots[slotKey]?.plannedSets.count ?? 0) + (added[slotKey] ?? 0)
    }

    /// Slots, in routine order, that can be logged (have a template ID) and still have working sets to do.
    /// No fixed order: the athlete can jump anywhere; the first one is only where the Watch goes next.
    public func pendingSlots(routineKey: String, session: Session?, added: [String: Int] = [:]) -> [String] {
        routines[routineKey]?.slots.filter { key in
            slots[key]?.templateId != nil
                && (session?.sets(forSlot: key).working.count ?? 0) < setCount(key, added: added)
        } ?? []
    }

    public func firstPendingSlot(routineKey: String, session: Session?, added: [String: Int] = [:]) -> String? {
        pendingSlots(routineKey: routineKey, session: session, added: added).first
    }
}

extension Sequence where Element == Session.SetEntry {
    /// The sets that count against the plan: everything but warm-ups (CONTEXT "Set type", N7).
    public var working: [Session.SetEntry] { filter { $0.type != .warmup } }
}

/// Where the Watch goes after Hecho (G39): the next slot, whether a rest runs first (its seconds; nil = no rest,
/// straight to a superset partner) and whether the next slot is only proposed (L4 / RT-04: Double Tap waits for a
/// touch). A superset's order is the coach's, not a guess, so moving inside a pair is never "proposed".
public struct AfterSet: Equatable, Sendable {
    public let next: String?
    public let rest: Int?
    public let proposed: Bool
    public init(next: String?, rest: Int?, proposed: Bool) { self.next = next; self.rest = rest; self.proposed = proposed }
}

extension Plan {
    /// The slot's superset in routine order, when at least two of its members can be logged; else empty.
    func supersetMembers(of key: String, routineKey: String) -> [String] {
        guard let id = slots[key]?.superset else { return [] }
        let members = (routines[routineKey]?.slots ?? []).filter { slots[$0]?.superset == id && slots[$0]?.templateId != nil }
        return members.count > 1 && members.contains(key) ? members : []
    }

    /// The member after this one in its superset (wrapping): the partner named on the Set page ("Superserie").
    public func supersetPartner(of key: String, routineKey: String) -> String? {
        let m = supersetMembers(of: key, routineKey: routineKey)
        return m.firstIndex(of: key).map { m[($0 + 1) % m.count] }
    }

    /// The routine's slots in order, consecutive superset members grouped (Overview, G39).
    public func supersetRuns(routineKey: String) -> [[String]] {
        var runs: [[String]] = []
        for key in routines[routineKey]?.slots ?? [] {
            // Both ends must be loggable members: an unloggable slot with the same id stays out of the group (N9).
            if let last = runs.last?.last, !supersetMembers(of: key, routineKey: routineKey).isEmpty,
               !supersetMembers(of: last, routineKey: routineKey).isEmpty, slots[last]?.superset == slots[key]?.superset {
                runs[runs.count - 1].append(key)
            } else {
                runs.append([key])
            }
        }
        return runs
    }

    /// After Hecho on `key` (G39). In a superset, a round is every member's set number n: while another member still
    /// has fewer than n working sets, go straight to it (the next one after `key`, wrapping) with no rest; once the
    /// round is complete, rest with the rest of the set just done, then the next member with sets to do. A finished
    /// partner, "+1 serie" or a warm-up on one member simply means an ordinary rest. Outside a superset (or with no
    /// member left): stay on the slot while it has sets, else propose the first pending slot (L4).
    public func afterSet(_ key: String, routineKey: String, session: Session, added: [String: Int] = [:]) -> AfterSet {
        let rest = slots[key]?.restSeconds
        func pending(_ k: String) -> Bool {
            slots[k]?.prefill(confirmed: session.sets(forSlot: k), added: added[k] ?? 0) != nil
        }
        let members = supersetMembers(of: key, routineKey: routineKey)
        if session.sets(forSlot: key).last?.type != .warmup, let i = members.firstIndex(of: key) { // a warm-up stays put
            let others = (members[(i + 1)...] + members[..<i]).filter(pending)
            let n = session.sets(forSlot: key).working.count
            if let behind = others.first(where: { session.sets(forSlot: $0).working.count < n }) {
                return AfterSet(next: behind, rest: nil, proposed: false)
            }
            if let next = others.first { return AfterSet(next: next, rest: rest, proposed: false) }
        }
        if pending(key) { return AfterSet(next: key, rest: rest, proposed: false) }
        return AfterSet(next: firstPendingSlot(routineKey: routineKey, session: session, added: added), rest: rest, proposed: true)
    }
}
