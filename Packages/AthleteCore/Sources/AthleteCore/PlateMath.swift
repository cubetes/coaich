import Foundation

/// Plates to load on each side of a bar for a target total, largest first (on the one sleeve when `sides` is 1).
/// `remainderPerSide` is what couldn't be matched with the available plates.
public struct PlateLoad: Equatable, Sendable {
    public let perSide: [Double]
    public let remainderPerSide: Double
}

public enum PlateMath {
    /// The owner's gym (2026-10): 20 kg bar, these plate sizes, unlimited pairs.
    public static let gymPlates: [Double] = [25, 20, 15, 10, 5, 2.5, 1.25]
    public static let bar = 20.0
    /// Smallest loadable change in total kg: the smallest plate on both sides (2,5).
    public static let step = 2 * gymPlates.min()!

    /// Where plates start (G68): the coach's `start_kg` (snapshot, companion PR #13; 0 = only the plates count), else
    /// the 20 kg bar on a barbell slot (older snapshots); nil = not plate-loaded. A negative `start_kg` is ignored.
    public static func startWeight(equipment: String?, startKg: Double? = nil) -> Double? {
        if let startKg, startKg >= 0 { return startKg }
        return equipment == "barbell" ? bar : nil
    }

    /// For a weight the plates can't make (G14: odd typed kg), the nearest loadable totals below and above, as the
    /// quiet hint; `below` is nil under the start weight. nil when `total` loads exactly.
    public static func nearestLoadable(total: Double, startWeight: Double = 20) -> (below: Double?, above: Double)? {
        let k = (total - startWeight) / step
        if total >= startWeight, abs(k - k.rounded()) < 1e-6 { return nil }
        guard total > startWeight else { return (nil, startWeight) }
        return (startWeight + k.rounded(.down) * step, startWeight + k.rounded(.up) * step)
    }

    /// `startWeight` is the bar (20) or 0 for plate-only machines (ADR scope Q25); `sides` 1 = one sleeve (G68).
    public static func load(total: Double, startWeight: Double = 20, sides: Int = 2, plates: [Double] = gymPlates) -> PlateLoad {
        var left = max(0, (total - startWeight) / Double(sides))
        var perSide: [Double] = []
        // Greedy is exact here: every size is a multiple of the smallest (1.25).
        for plate in plates.sorted(by: >) {
            while left + 1e-9 >= plate {
                perSide.append(plate)
                left -= plate
            }
        }
        return PlateLoad(perSide: perSide, remainderPerSide: (left * 1000).rounded() / 1000)
    }

    /// The kg per side (on the sleeve, one-sleeve) the plates can't make, for the Set page's non-blocking hint
    /// ("No cargable · +0,62/lado"); nil for a loadable weight or one under the start (the plate line says that).
    public static func unloadablePerSide(total: Double, startWeight: Double, sides: Int = 2) -> Double? {
        guard total > startWeight else { return nil }
        let r = load(total: total, startWeight: startWeight, sides: sides).remainderPerSide
        return r > 0 ? r : nil
    }

    /// The plate line (G68, panel copy): plates count first, repeats grouped so they never read as "kg × reps"
    /// ("2×25 · 10"), and what the plates can't make as a caution `warning` ("+0,5/lado"; one sleeve "+1 kg").
    /// Edge strings: "Solo la barra" / "Sin discos" (start 0) at the start weight, "Menos que la barra (20)" under it.
    public struct Line: Equatable, Sendable {
        public let text: String
        public let warning: String?
        public init(text: String, warning: String?) { self.text = text; self.warning = warning }
    }

    public static func line(total: Double, start: Double, sides: Int = 2) -> Line {
        if total < start - 1e-9 { return Line(text: "", warning: "Menos que la barra (\(kg(start)))") }
        let load = load(total: total, startWeight: start, sides: sides)
        let groups = grouped(load.perSide).map { $0.count > 1 ? "\($0.count)×\(kg($0.plate))" : kg($0.plate) }
        let text = groups.isEmpty ? (start > 0 ? "Solo la barra" : "Sin discos") : groups.joined(separator: " · ")
        let r = load.remainderPerSide
        return Line(text: text, warning: r > 0 ? "+\(kg(r, down: true))\(sides == 1 ? " kg" : "/lado")" : nil)
    }

    /// VoiceOver for the plate line (panel lens 3): "Por lado: 2 de 25 y 1 de 10; faltan 0,5 por lado".
    public static func spoken(total: Double, start: Double, sides: Int = 2) -> String {
        let l = line(total: total, start: start, sides: sides)
        let load = load(total: total, startWeight: start, sides: sides)
        let parts = grouped(load.perSide).map { "\($0.count) de \(kg($0.plate))" }
        guard let last = parts.last else { return l.text.isEmpty ? l.warning ?? "" : l.text } // bar only / under the bar
        let list = parts.count > 1 ? parts.dropLast().joined(separator: ", ") + " y " + last : last
        let r = load.remainderPerSide
        let missing = r > 0 ? "; faltan \(kg(r, down: true))\(sides == 1 ? " kilos" : " por lado")" : ""
        return "\(sides == 1 ? "Discos" : "Por lado"): \(list)\(missing)"
    }

    private static func grouped(_ plates: [Double]) -> [(plate: Double, count: Int)] {
        var out: [(plate: Double, count: Int)] = []
        for p in plates {
            if out.last?.plate == p { out[out.count - 1].count += 1 } else { out.append((p, 1)) }
        }
        return out
    }

    /// Spanish kg: "1,25", "0,62" (a remainder rounds down, so it never claims more than is missing).
    private static func kg(_ v: Double, down: Bool = false) -> String {
        v.formatted(.number.precision(.fractionLength(0...2)).rounded(rule: down ? .down : .toNearestOrEven)
            .locale(Locale(identifier: "es_ES")))
    }
}
