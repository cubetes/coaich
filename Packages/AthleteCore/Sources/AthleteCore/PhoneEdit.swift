import Foundation

// The iPhone's side of M3 (v0.6.0): the 24 h edit view's grouping (G70) and the "Otro (en el iPhone)" list (G69).

extension Session {
    /// One slot of the read/edit view (panel must-fix 23): its exercise entries in order — more than one after a
    /// swap — each with the slot-level index of its first set, the `index:` every set edit takes.
    public struct SlotGroup: Equatable, Sendable {
        public let slot: String
        public let entries: [Entry]
        public struct Entry: Equatable, Sendable {
            /// Position in `exercises`.
            public let position: Int
            /// Slot-level index of this entry's first set.
            public let offset: Int
        }
    }

    /// Slots in the order first done.
    public var slotGroups: [SlotGroup] {
        var order: [String] = []
        for e in exercises where !order.contains(e.slot) { order.append(e.slot) }
        return order.map { slot in
            var offset = 0
            let entries = exercises.indices.filter { exercises[$0].slot == slot }.map { i in
                defer { offset += exercises[i].sets.count }
                return SlotGroup.Entry(position: i, offset: offset)
            }
            return SlotGroup(slot: slot, entries: entries)
        }
    }
}

extension Plan {
    public struct Choice: Hashable, Sendable {
        public let templateId: String
        public let name: String
        /// Hevy primary muscle (G73); nil from an older snapshot.
        public let primaryMuscle: String?
        public var group: MuscleGroup? { MuscleGroup(hevy: primaryMuscle) }
    }

    /// "Otro (en el iPhone)" (G69, owner: the ~100 plan exercises): the slot's own coach alternatives first, then every
    /// other exercise in the plan — each slot's own and its alternatives — once per template id, by name.
    public func swapChoices(slot key: String) -> (coach: [Choice], plan: [Choice]) {
        let coach = (slots[key]?.alternatives ?? []).map { Choice(templateId: $0.templateId, name: $0.name, primaryMuscle: $0.primaryMuscle) }
        var seen = Set(coach.map(\.templateId))
        var rest: [Choice] = []
        for slot in slots.keys.sorted().compactMap({ slots[$0] }) { // sorted: the same name wins every time
            let own = slot.templateId.map { [Choice(templateId: $0, name: slot.name, primaryMuscle: slot.primaryMuscle)] } ?? []
            for c in own + (slot.alternatives ?? []).map({ Choice(templateId: $0.templateId, name: $0.name, primaryMuscle: $0.primaryMuscle) })
            where seen.insert(c.templateId).inserted {
                rest.append(c)
            }
        }
        return (coach, rest.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending })
    }
}

/// The iPhone "Otro" filter chips (G73), in chip order. Hevy's primary muscles map onto them; anything else
/// (full_body, cardio, other, neck, unknown) has no group and shows only under "Todos".
public enum MuscleGroup: CaseIterable, Sendable {
    case chest, back, shoulders, arms, legs, core

    public var label: String {
        switch self {
        case .chest: "Pecho"
        case .back: "Espalda"
        case .shoulders: "Hombro"
        case .arms: "Brazos"
        case .legs: "Pierna"
        case .core: "Core"
        }
    }

    public init?(hevy: String?) {
        switch hevy?.lowercased() {
        case "chest": self = .chest
        case "lats", "upper_back", "lower_back", "traps": self = .back
        case "shoulders": self = .shoulders
        case "biceps", "triceps", "forearms": self = .arms
        case "quadriceps", "hamstrings", "glutes", "calves", "abductors", "adductors": self = .legs
        case "abdominals": self = .core
        default: return nil
        }
    }

    /// The chips to show: groups with at least one exercise. Empty (no chips) when no choice has a muscle.
    public static func chips(for choices: [Plan.Choice]) -> [MuscleGroup] {
        allCases.filter { g in choices.contains { $0.group == g } }
    }
}
