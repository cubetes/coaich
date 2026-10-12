import ActivityKit
import SwiftUI
import AthleteCore

// Compiled into both the iPhone app and the Live Activity extension (AthleteCore also builds for watchOS,
// which has no ActivityKit, so this can't live there).

/// The app theme (G43/L14), chosen on the iPhone's Home. Raw values are the `@AppStorage("theme")` and Watch
/// application-context values.
nonisolated enum AppTheme: String, Codable, Hashable, CaseIterable {
    case magenta, neon
}

/// The lock-screen panel's data is the Watch's live state, as it arrives over the mirrored workout.
nonisolated struct WorkoutAttributes: ActivityAttributes {
    /// Carried in the activity because the extension can't read the app's settings without an App Group, which a
    /// free Personal Team can't sign. Static per activity: a change mid-session shows on the next one.
    var theme: AppTheme = .magenta

    struct ContentState: Codable, Hashable {
        var live: LiveState
        /// When the phone got it: the stale panel's "Sin datos del reloj desde las 7:24".
        var receivedAt: Date
        /// G53: cues are on but the phone's audio couldn't start; the panel says "Abre la app para los sonidos".
        /// Optional so states encoded before v0.4.4 still decode.
        var soundOff: Bool? = nil
    }
}

extension LiveState {
    /// "Serie 3/4", or "Calent." for a warm-up (G32).
    var setLabel: String? {
        if warmup == true { return "Calent." }
        return setNumber.map { n in setsPlanned.map { "Serie \(n)/\($0)" } ?? "Serie \(n)" }
    }

    /// VoiceOver: "serie 3 de 4", never "S3/4" letter by letter.
    var setSpoken: String? {
        if warmup == true { return "calentamiento" }
        return setNumber.map { n in setsPlanned.map { "serie \(n) de \($0)" } ?? "serie \(n)" }
    }

    /// Nothing left to log (LA-06): no exercise proposed and every working set done. An older Watch sends no
    /// segments and nil set numbers on warm-ups, so it never claims "Todo hecho" (red team S1).
    var allDone: Bool {
        guard let segments else { return false }
        return exercise == nil && segments.allSatisfy { $0.done >= $0.planned }
    }
}

/// Rest countdown while resting (`isResting`, LA-03), the 3-2-1 before "¡Vamos!", otherwise elapsed session time.
/// The caller reads `now` once, so layout, caption and clock agree and no range is ever built backwards.
struct LiveClock: View {
    let state: LiveState
    var now = Date.now

    var body: some View {
        if state.isResting(at: now), let end = state.restEnd {
            Text(timerInterval: now...end, countsDown: true)
        } else if let go = state.go, go > now {
            Text(timerInterval: now...go, countsDown: true)
        } else {
            Text(state.startedAt, style: .timer)
        }
    }
}
