import ActivityKit
import SwiftUI
import WidgetKit
import AthleteCore

@main
struct LiveActivityBundle: WidgetBundle {
    var body: some Widget { WorkoutLiveActivity() }
}

/// Design D "Mezcla" (G32–G36, docs/design/live-activity/final.html). Never alerts (R9), no buttons, no `.small`.
struct WorkoutLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: WorkoutAttributes.self) { context in
            LockScreen(state: context.state.live, receivedAt: context.state.receivedAt, isStale: context.isStale,
                       soundOff: context.state.soundOff == true, theme: context.attributes.theme)
                .activityBackgroundTint(.black)   // R1: our colours only pass on black, also in Light Mode
                .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            let s = context.state.live
            let now = Date.now
            let rest = context.isStale ? nil : s.restRange(at: now)
            return DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Group {
                        if context.isStale {
                            Image(systemName: "applewatch.slash").foregroundStyle(Theme.caution)
                        } else if let rest {
                            HStack(spacing: 8) {
                                Ring(range: rest).frame(width: 32, height: 32)
                                Text("Descanso").font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.elapsed)
                            }
                        } else {
                            HStack(alignment: .firstTextBaseline, spacing: 6) {
                                Glyph()
                                Text(s.exercise ?? s.routineTitle).lineLimit(2)
                            }
                            .font(.system(size: 17, weight: .semibold))
                        }
                    }
                    .padding(.leading, 8)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Group {
                        if context.isStale {
                            EmptyView()
                        } else if let rest {
                            Countdown(range: rest, template: "00:00").font(Theme.num(32)).foregroundStyle(Theme.elapsed)
                        } else if let set = s.setLabel {
                            Text(set).font(.system(size: 15, weight: .semibold))
                        }
                    }
                    .padding(.trailing, 8)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Group {
                        if context.isStale {
                            StaleView(state: s, receivedAt: context.state.receivedAt)
                        } else if rest != nil {
                            NextLine(state: s)
                        } else if let kg = s.targetKg, let reps = s.targetReps {
                            Target(kg: kg, reps: reps, size: 28)
                        }
                    }
                    .padding(.horizontal, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            } compactLeading: {
                if context.isStale {
                    Image(systemName: "applewatch.slash").foregroundStyle(Theme.caution)
                } else {
                    Glyph()
                }
            } compactTrailing: {
                if context.isStale {
                    Text("–:––").font(Theme.num(15)).foregroundStyle(.secondary)
                } else if let rest { // G72: owner-tested variant 2; the dumbbell leads, the countdown trails
                    Text(timerInterval: rest, countsDown: true, showsHours: false).font(Theme.num(11)).foregroundStyle(Theme.elapsed)
                        .multilineTextAlignment(.center).frame(width: 40)
                        .accessibilityLabel(Text("Descanso, quedan \(Text(timerInterval: rest, countsDown: true))"))
                } else if let short = s.islandSet {
                    Text(short).font(Theme.num(15)).accessibilityLabel(s.setSpoken ?? short)
                }
            } minimal: {
                if context.isStale {
                    Image(systemName: "applewatch.slash").foregroundStyle(Theme.caution)
                } else if let rest { // G54: timer text ignores minimumScaleFactor; a fixed 12 pt "1:30" fits beside Spotify
                    Text(timerInterval: rest, countsDown: true, showsHours: false).font(Theme.num(12)).foregroundStyle(Theme.elapsed)
                        .lineLimit(1).multilineTextAlignment(.center).frame(maxWidth: .infinity)
                } else if let short = s.islandSet {
                    Text(short).font(Theme.num(15)).minimumScaleFactor(0.8).accessibilityLabel(s.setSpoken ?? short)
                } else {
                    Glyph()
                }
            }
            .keylineTint(Theme.accent)
        }
    }
}

// MARK: - Tokens (DESIGN.md §2; the panel is always black, R1)

enum Theme {
    static let accent = Color(red: 1, green: 0x3D / 255, blue: 0x6E / 255)               // #FF3D6E kg, glyph, frame (G83, = Watch)
    static let hit = Color(red: 0x2B / 255, green: 0xD2 / 255, blue: 0x7A / 255)         // #2BD27A reps, done sets
    static let elapsed = Color(red: 1, green: 0xD6 / 255, blue: 0x0A / 255)              // #FFD60A rest, Sesión time
    static let caution = Color(red: 1, green: 0xB0 / 255, blue: 0x2E / 255)              // #FFB02E stale
    static let track = Color(red: 0x3A / 255, green: 0x3A / 255, blue: 0x3C / 255)       // #3A3A3C pending sets
    /// E2 "Brillo magenta" glow (G35). The one value the L14 theme (Magenta / Neón verde) switches.
    static let glow = Color(red: 0xDE / 255, green: 0x14 / 255, blue: 0x46 / 255)        // #DE1446 (G83, = Watch accentFill)
    /// The Watch's neon accent; the glow in the Neón verde theme.
    static let neonAccent = Color(red: 0xB4 / 255, green: 0xF0 / 255, blue: 0x3C / 255)  // #B4F03C
    /// Black with a soft 24 % glow from the top-right corner; static per update.
    static func background(_ theme: AppTheme) -> some View {
        let glow = theme == .neon ? neonAccent : Self.glow
        return ZStack {
            Color.black
            EllipticalGradient(colors: [glow.opacity(0.24), glow.opacity(0)], center: .topTrailing,
                               startRadiusFraction: 0, endRadiusFraction: 0.8)
        }
    }
    /// Opens the app on Home, whose first section is "Sesión en curso" (R7).

    static func num(_ size: CGFloat) -> Font { .system(size: size, weight: .semibold, design: .rounded).monospacedDigit() }
}

/// Lock-screen text that follows Dynamic Type (capped at .large so the panel stays ≤ 160 pt). Hero numerals are fixed.
enum TypeScale {
    static let exercise = Font.title3.weight(.semibold)                                       // 20
    static let label = Font.headline                                                          // 17 semibold
    static let body = Font.body                                                               // 17
    static let routine = Font.subheadline                                                     // 15
    static let caption = Font.footnote.weight(.medium)                                        // 13
    static let elapsed = Font.system(.title2, design: .rounded, weight: .semibold).monospacedDigit()  // 22
    static let count = Font.system(.subheadline, design: .rounded, weight: .semibold).monospacedDigit() // 15
}

extension LiveState {
    /// The rest range if resting now (the one rule, LA-03); the bar and ring drain from `restStart` (R6), or from
    /// now when an older Watch sends none. Never a backwards range.
    func restRange(at now: Date) -> ClosedRange<Date>? {
        guard isResting(at: now), let end = restEnd else { return nil }
        return (restStart.flatMap { $0 < end ? $0 : nil } ?? now)...end
    }

    /// Island set label: "3/4", "CAL" for a warm-up.
    var islandSet: String? {
        if warmup == true { return "CAL" }
        return setNumber.map { n in setsPlanned.map { "\(n)/\($0)" } ?? "\(n)" }
    }
}

// MARK: - Lock Screen

private struct LockScreen: View {
    let state: LiveState
    let receivedAt: Date
    let isStale: Bool
    let soundOff: Bool
    let theme: AppTheme
    @Environment(\.isLuminanceReduced) private var dimmed

    var body: some View {
        let now = Date.now
        Group {
            if isStale {
                StaleView(state: state, receivedAt: receivedAt)
            } else if let rest = state.restRange(at: now) {
                restCard(rest)
            } else {
                setCard(now: now)
            }
        }
        .padding(14)   // R4: Apple's Live Activity margin
        .frame(maxWidth: .infinity, minHeight: 84, alignment: .leading)   // Apple's minimum; stale is shorter
        .foregroundStyle(.white)
        .background(Theme.background(theme))
        .dynamicTypeSize(...DynamicTypeSize.large) // .xLarge measured 159 of 160 pt resting (red team S3)
    }

    private func restCard(_ rest: ClosedRange<Date>) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Descanso").font(TypeScale.label).foregroundStyle(Theme.elapsed)
                    if soundOff { SoundHint() } else { RoutineLine(title: state.routineTitle) } // G53: in place, panel ≤ 160 pt
                }
                Spacer(minLength: 0)
                Countdown(range: rest, template: "00:00").font(Theme.num(56)).foregroundStyle(Theme.elapsed)
                    .padding(.vertical, -6)   // trim the font's line gap to the mockup's line-height 1
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(Text("Descanso, quedan \(Text(timerInterval: rest, countsDown: true))"))
            if !dimmed {   // LA-15: no bars in Always On, the digits stay
                ProgressView(timerInterval: rest, countsDown: true, label: { EmptyView() }, currentValueLabel: { EmptyView() })
                    .progressViewStyle(.linear).tint(Theme.elapsed)
                    .scaleEffect(x: 1, y: 2, anchor: .center).frame(height: 8).clipped()
                    .padding(.top, 6)
                    .accessibilityHidden(true)
            }
            if state.allDone || (state.exercise != nil && (state.segments != nil || state.setNumber != nil)) {
                NextLine(state: state).font(TypeScale.body).padding(.top, 8)
            }
            bar.padding(.top, 12)
        }
    }

    private func setCard(now: Date) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Glyph()
                    Text(state.exercise ?? state.routineTitle).lineLimit(1).minimumScaleFactor(0.85) // shrink a little before cutting
                }
                .font(TypeScale.exercise)
                Spacer(minLength: 0)
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(state.go.map { $0 > now } == true ? "Empieza" : "Sesión")   // LA-16
                        .font(TypeScale.caption).foregroundStyle(.secondary)
                    Text("0:00:00").hidden()   // fixed width for 1:02:10: the panel never jumps after an hour
                        .overlay(alignment: .trailing) { LiveClock(state: state, now: now).multilineTextAlignment(.trailing) }
                        .font(TypeScale.elapsed).foregroundStyle(Theme.elapsed)
                }
                .fixedSize()
            }
            .accessibilityElement(children: .combine)
            if state.exercise != nil || soundOff {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    if state.exercise != nil, let kg = state.targetKg, let reps = state.targetReps {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text("Obj").font(TypeScale.caption).foregroundStyle(.secondary)
                            Target(kg: kg, reps: reps, size: 44)
                        }
                        .fixedSize()
                        .padding(.vertical, -4)
                    }
                    Spacer(minLength: 0)
                    if soundOff { // G53: in place of "Serie 3/4" (the bar still shows the sets); panel ≤ 160 pt
                        SoundHint()
                    } else if state.exercise != nil, let set = state.setLabel {
                        Text(set).font(TypeScale.label).accessibilityLabel(state.setSpoken ?? set)
                    }
                }
                .padding(.top, 14)
            }
            bar.padding(.top, 12)
        }
    }

    @ViewBuilder private var bar: some View {
        if let segments = state.segments, !dimmed { WorkoutBar(segments: segments, current: state.current) }
    }
}

/// Stale (R5, LA-05): no update from the Watch for 20 min, or 30 s past a rest's end. Routine only under it.
private struct StaleView: View {
    let state: LiveState
    let receivedAt: Date

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Label {
                Text("Sin datos del reloj desde las \(receivedAt.formatted(date: .omitted, time: .shortened))")
            } icon: {
                Image(systemName: "applewatch.slash")
            }
            .font(TypeScale.label).foregroundStyle(Theme.caution)
            RoutineLine(title: state.routineTitle)
        }
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Pieces

private struct Glyph: View {
    var body: some View {
        Image(systemName: "dumbbell.fill").imageScale(.small).foregroundStyle(Theme.accent).accessibilityHidden(true)
    }
}

private struct RoutineLine: View {
    let title: String
    var body: some View {
        HStack(spacing: 5) {
            Glyph()
            Text(title).lineLimit(1)
        }
        .font(TypeScale.routine).foregroundStyle(.secondary)
    }
}

/// G53: cues are on but iOS refused to start the phone's audio from the background; opening the app once starts it.
private struct SoundHint: View {
    var body: some View {
        ViewThatFits(in: .horizontal) { // beside a wide "102.5 kg × 10" target only the short form fits
            Text("\(Image(systemName: "speaker.slash.fill")) Abre la app para los sonidos")
            Text("\(Image(systemName: "speaker.slash.fill")) Abre la app")
        }
        .font(TypeScale.caption).foregroundStyle(Theme.caution).lineLimit(1)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Sin sonidos: abre la app para activarlos")
    }
}

/// A self-running countdown in a fixed frame sized by `template`, so nothing around it moves as it ticks.
private struct Countdown: View {
    let range: ClosedRange<Date>
    let template: String
    var showsHours = true
    var body: some View {
        Text(template).hidden()
            .overlay(alignment: .trailing) {
                Text(timerInterval: range, countsDown: true, showsHours: showsHours).multilineTextAlignment(.trailing)
            }
    }
}

private struct Ring: View {
    let range: ClosedRange<Date>
    @Environment(\.isLuminanceReduced) private var dimmed
    var body: some View {
        if !dimmed {
            ProgressView(timerInterval: range, countsDown: true, label: { EmptyView() }, currentValueLabel: { EmptyView() })
                .progressViewStyle(.circular).tint(Theme.elapsed)
                .accessibilityHidden(true)
        }
    }
}

/// "100 kg × 8": kg pink, reps green (the Watch's kg/reps colours); the unit small (G45).
private struct Target: View {
    let kg: Double
    let reps: Int
    let size: CGFloat
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            Text(kg.formatted()).foregroundStyle(Theme.accent)
            Text("kg").font(.system(size: size * 0.4, weight: .semibold, design: .rounded)).foregroundStyle(Theme.accent)
            Text("×").font(.system(size: size * 0.64, design: .rounded)).foregroundStyle(.secondary)
            Text("\(reps)").foregroundStyle(Theme.hit)
        }
        .font(Theme.num(size))
        .fixedSize()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Objetivo \(kg.formatted()) kilos por \(reps)")
    }
}

/// "Siguiente  Press banca inclinado · 3/4 · 100 kg × 8" (G36, G45, G48): only the name ever shortens.
private struct NextLine: View {
    let state: LiveState
    var body: some View {
        if state.allDone {
            Text("Todo hecho · termina en el reloj")
        } else if let exercise = state.exercise {
            let set = (state.warmup == true ? state.setLabel : state.islandSet).map { " · \($0)" } ?? "" // "3/4" (G48), "Calent."
            HStack(alignment: .firstTextBaseline, spacing: 0) {
                Text("Siguiente").fontWeight(.semibold).foregroundStyle(Theme.elapsed).padding(.trailing, 6)
                Text(exercise).lineLimit(1)
                Text(set).fixedSize()
                if let kg = state.targetKg, let reps = state.targetReps {
                    Text(" · ").fixedSize()
                    Text("\(Text("\(kg.formatted()) kg").foregroundStyle(Theme.accent))\(Text(" × ").foregroundStyle(.secondary))\(Text("\(reps)").foregroundStyle(Theme.hit))")
                        .fixedSize()
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Siguiente: \(exercise)\(state.setSpoken.map { ", \($0)" } ?? "")\(state.targetKg.flatMap { kg in state.targetReps.map { ", \(kg.formatted()) kilos por \($0)" } } ?? "")")
        }
    }
}

/// Workout bar (G33): one segment per exercise, width ∝ planned working sets, 2 pt gaps; done sets green, the
/// current exercise framed in the accent, pending grey; "9/17" from the segments only (never `setsLogged`).
private struct WorkoutBar: View {
    let segments: [LiveState.Segment]
    let current: Int?

    var body: some View {
        let shown = segments.indices.filter { segments[$0].planned > 0 }
        let planned = segments.reduce(0) { $0 + $1.planned }
        let done = segments.reduce(0) { $0 + min($1.done, $1.planned) }
        if planned > 0 {
            HStack(spacing: 10) {
                GeometryReader { g in
                    let unit = max(0, g.size.width - 2 * CGFloat(shown.count - 1)) / CGFloat(planned)
                    HStack(spacing: 2) {
                        ForEach(shown, id: \.self) { i in
                            segment(segments[i], width: unit * CGFloat(segments[i].planned), current: i == current)
                        }
                    }
                }
                .frame(height: 10)
                Text("\(done)/\(planned)").font(TypeScale.count)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(done) de \(planned) series")
        }
    }

    private func segment(_ s: LiveState.Segment, width: CGFloat, current: Bool) -> some View {
        ZStack(alignment: .leading) {
            Rectangle().fill(current ? Color.clear : Theme.track)
            Rectangle().fill(Theme.hit).frame(width: width * CGFloat(min(s.done, s.planned)) / CGFloat(s.planned))
        }
        .frame(width: width, height: 10)
        .clipShape(RoundedRectangle(cornerRadius: 2))
        .overlay { if current { RoundedRectangle(cornerRadius: 2.5).strokeBorder(Theme.accent, lineWidth: 1.5) } }
    }
}
