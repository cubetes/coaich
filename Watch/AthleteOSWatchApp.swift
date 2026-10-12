import SwiftUI
import WatchKit
import HealthKit
import AthleteCore

// The Watch app. Screens live in Screens.swift; this file holds the app entry, the design tokens and the
// shared components. Every value here is specified in docs/design/DESIGN.md — change both together.

@main
struct AthleteOSWatchApp: App {
    @WKApplicationDelegateAdaptor private var delegate: AppDelegate
    private var model: WatchModel { delegate.model }

    var body: some Scene {
        WindowGroup {
            NavigationStack {
                if model.countdown != nil { CountdownView() } // L9; the session starts underneath at "¡Vamos!"
                else if model.session != nil { SessionView().demoXL() }
                else if model.finished != nil { FinishedView() } // G41 summary, then G42 "¿Cómo ha ido?"
                else { RoutinePicker() }
            }
            .id(model.neon) // G43: a theme change redraws everything (applied only outside a session)
            .environment(model)
        }
    }
}

/// Owns the model so the phone's workout launch can reach it (start from iPhone, G15).
final class AppDelegate: NSObject, WKApplicationDelegate {
    let model = WatchModel()

    func handle(_ workoutConfiguration: HKWorkoutConfiguration) { model.phoneLaunched() }
}

// MARK: - Tokens (DESIGN.md § Tokens)

enum Theme {
    /// Neón verde theme (G43), set by `WatchModel.applyTheme`; the root view is re-identified when it changes.
    static var neon = false
    /// The Neón verde accent, fill and text alike: black label 15.47:1, 15.47:1 on black, 11.58:1 on clear glass.
    static let neonGreen = Color(red: 0xB4 / 255, green: 0xF0 / 255, blue: 0x3C / 255)   // #B4F03C
    /// Filled accent (Hecho, selected RIR, keypad OK, Terminar): MAGMA magenta (G83) one step darker, white label
    /// 4.89:1; neon, black label.
    static var accentFill: Color { neon ? neonGreen : Color(red: 0xDE / 255, green: 0x14 / 255, blue: 0x46 / 255) } // #DE1446
    /// Accent for text, strokes and focus rings on black: MAGMA's dark-mode #FF3D6E (G83) 6.14:1; neon 15.47:1.
    static var accent: Color { neon ? neonGreen : Color(red: 1, green: 0x3D / 255, blue: 0x6E / 255) }             // #FF3D6E
    /// Label on `accentFill`: white on magenta, black on neon green (white would be 1.36:1).
    static var onAccent: Color { neon ? .black : .white }
    /// Logged / done (Registrada ✓, Completado, ✓, Enviado ✓): green, or white in neon — green is the accent there.
    static var done: Color { neon ? .white : hit }
    /// Done / logged / sent. Black label on it (10.6:1); never a white label.
    static let hit = Color(red: 0x2B / 255, green: 0xD2 / 255, blue: 0x7A / 255)         // #2BD27A
    /// Warm-up badge, "Por enviar", loadability warning.
    static let caution = Color(red: 1, green: 0xB0 / 255, blue: 0x2E / 255)              // #FFB02E
    /// FALLO badge, heart, RIR 0, Descartar: a true red re-tuned for the MAGMA accent (G83): ΔE 44 from `accent`,
    /// 36 from `accentFill`, 32 from RIR 1 orange; black label 6.04:1, 4.52:1 on clear glass.
    static let missed = Color(red: 1, green: 0x42 / 255, blue: 0x18 / 255)               // #FF4218
    /// Drop badge and added rest time.
    static let violet = Color(red: 0xA7 / 255, green: 0x8B / 255, blue: 0xFA / 255)      // #A78BFA
    /// Elapsed time, countdown, "Siguiente" label — Apple Workout's yellow.
    static let elapsed = Color(red: 1, green: 0xD6 / 255, blue: 0x0A / 255)              // #FFD60A
    /// RIR chips 0 · 1 · 2 · 3+ (G7): red, orange, yellow, green. Black label on each ≥ 6.04:1.
    static let rir = [missed, Color(red: 1, green: 0x8A / 255, blue: 0x3D / 255), elapsed, hit] // orange #FF8A3D
    /// Kg / reps metric captions.
    static var kgColor: Color { accent }
    /// Reps: green, or white in Neón verde — lime kg beside green reps read alike (G58).
    static var repsColor: Color { neon ? .white : hit }
    /// Heart-rate zones Z1…Z5 (Métricas): blue, green, yellow, orange, red — always shown with "Z1…Z5" text.
    static let zones = [Color(red: 0x5A / 255, green: 0xC8 / 255, blue: 0xFA / 255), hit, elapsed, caution, missed]
    /// The colour a filled control turns into as text/stroke (Always On, covered): accentFill → accent.
    static func stroke(_ fill: Color) -> Color { fill == accentFill ? accent : fill }
    /// The label colour on a tinted control: `onAccent` on the accent, black on green / white (done), else white.
    static func label(on tint: Color?) -> Color {
        guard let tint else { return .white }
        return tint == accentFill ? onAccent : tint == hit || tint == .white ? .black : .white
    }
}

enum Metrics {
    /// Big kg/reps numerals: fixed size (not a text style), rounded, monospaced digits.
    static let numeral: CGFloat = 34
    static let countdown: CGFloat = 44
    static let primaryHeight: CGFloat = 40
    static let sidePadding: CGFloat = 9
    static let boxHeight: CGFloat = 46
    static let arrowSize = CGSize(width: 38, height: 28)
    /// Space kept free at the bottom of the Set/Rest pages so nothing sits under the page dots (G5).
    static let dotsClearance: CGFloat = 12
}

/// Spanish number format everywhere ("97,5 × 12"), whatever the Watch's own region is.
enum Fmt {
    static let es = Locale(identifier: "es_ES")
    static func kg(_ v: Double) -> String { v.formatted(.number.precision(.fractionLength(0...2)).locale(es)) }
    static func set(_ kg: Double?, _ reps: Int?) -> String {
        "\(kg.map(Fmt.kg) ?? "—") × \(reps.map(String.init) ?? "—")"
    }
    /// Snapshot history top set "97.5×12" → "97,5 × 12".
    static func top(_ s: String) -> String {
        let parts = s.split(separator: "×")
        guard parts.count == 2, let kg = Double(parts[0].trimmingCharacters(in: .whitespaces)) else { return s }
        return "\(Fmt.kg(kg)) × \(parts[1].trimmingCharacters(in: .whitespaces))"
    }
    /// Rest time added on this rest: "+30 s" / "−15 s".
    static func nudge(_ seconds: Int) -> String { "\(seconds < 0 ? "−" : "+")\(abs(seconds)) s" }
    static func routine(_ exercises: Int, _ sets: Int) -> String {
        "\(exercises) \(exercises == 1 ? "ejercicio" : "ejercicios") · \(sets) \(sets == 1 ? "serie" : "series")"
    }
    /// Rep list with hyphens ("12-12-10"); the middle dot only separates fields.
    static func reps(_ list: [Int]) -> String { list.map(String.init).joined(separator: "-") }
    /// "0,62" per side.
    static func perSide(_ v: Double) -> String { v.formatted(.number.precision(.fractionLength(0...2)).rounded(rule: .down).locale(es)) }
    /// Whole number, Spanish grouping ("8450", "12.450").
    static func whole(_ v: Double) -> String { v.formatted(.number.precision(.fractionLength(0)).locale(es)) }
    /// "1:29:07" / "45:12" (the summary's session time).
    static func duration(_ s: TimeInterval) -> String {
        let t = Int(s.rounded(.down)), h = t / 3600, m = t / 60 % 60, sec = t % 60
        return h > 0 ? String(format: "%d:%02d:%02d", h, m, sec) : String(format: "%d:%02d", m, sec)
    }
    /// "41 min" (under a minute: "0 min").
    /// "mié 07:12" (routine list, G12).
    static func dayTime(_ d: Date) -> String {
        "\(d.formatted(.dateTime.weekday(.abbreviated).locale(es)).trimmingCharacters(in: .punctuationCharacters)) \(time(d))"
    }
    /// RIR as shown: "0"…"2", "3+".
    static func rir(_ v: Int) -> String { v >= 3 ? "3+" : "\(v)" }
    static func time(_ d: Date) -> String { d.formatted(.dateTime.hour(.twoDigits(amPM: .omitted)).minute().locale(es)) }
}

enum SyncState { case empty, pending, onPhone, sent, rejected }

enum Field: Identifiable { case kg, reps; var id: Self { self } }

extension Session.SetType {
    /// Menu word (sentence case).
    var spanish: String {
        switch self { case .warmup: "Calentamiento"; case .normal: "Normal"; case .failure: "Fallo"; case .dropset: "Drop" }
    }
    var badge: String? {
        switch self { case .warmup: "CAL"; case .normal: nil; case .failure: "FALLO"; case .dropset: "DROP" }
    }
    /// Compact chip letter (Resumen, G2).
    var letter: String {
        switch self { case .warmup: "C"; case .normal: ""; case .failure: "F"; case .dropset: "D" }
    }
    var color: Color {
        switch self { case .warmup: Theme.caution; case .normal: .white; case .failure: Theme.missed; case .dropset: Theme.violet }
    }
}

// MARK: - Components (DESIGN.md § Components)

extension View {
    /// DEBUG `-demoDimmed`: draw as if the wrist were down.
    @ViewBuilder func demoDimmed() -> some View {
        #if DEBUG
        if Demo.dimmed { environment(\.isLuminanceReduced, true) } else { self }
        #else
        self
        #endif
    }

    /// `-demoXL`: the largest text size the session pages allow (`.xLarge`), for the worst-case screenshots (G79).
    @ViewBuilder func demoXL() -> some View {
        #if DEBUG
        if Demo.xl { environment(\.dynamicTypeSize, .xLarge) }
        else if Demo.ax { environment(\.dynamicTypeSize, .accessibility3) } else { self }
        #else
        self
        #endif
    }

    /// Every session page fills the screen from the very top (the clock row is drawn around, not pushed),
    /// so no page shifts when content or the page changes.
    func sessionPage() -> some View {
        frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .ignoresSafeArea(edges: [.top, .bottom])
    }
}

/// System Liquid Glass on every button (L11): the system glass material (`glassEffect`, interactive) in the
/// control's exact frame. `tint` nil → clear glass (secondary controls); a tint → tinted glass (Hecho).
/// Not `.buttonStyle(.glass / .glassProminent)`: on watchOS 27 those impose the system's minimum button size
/// and padding (Saltar grew past its 30 pt row, ±15 past 40 pt and the countdown truncated), which breaks the
/// fixed Set/Rest layout. Wrist down, or under a sheet/dialog: an outline instead — no filled shapes in Always
/// On, no accent glow behind glass sheets (DESIGN §6). Reduce Transparency: the system makes the glass opaque.
struct GlassButton: ViewModifier {
    var tint: Color?
    var covered = false
    var radius: CGFloat = 20
    @Environment(\.isLuminanceReduced) private var dim

    func body(content: Content) -> some View {
        if dim || covered {
            content.buttonStyle(OutlineStyle(color: tint.map(Theme.stroke) ?? .white, radius: radius, prominent: tint != nil))
        } else {
            content.buttonStyle(GlassStyle(tint: tint, radius: radius))
        }
    }
}

struct GlassStyle: ButtonStyle {
    let tint: Color?
    let radius: CGFloat
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        let shape = RoundedRectangle(cornerRadius: radius)
        configuration.label
            .foregroundStyle(Theme.label(on: tint).opacity(enabled ? 1 : 0.3))
            .contentShape(shape)
            .glassEffect(tint.map { .regular.tint($0).interactive() } ?? .regular.interactive(), in: shape)
    }
}

extension View {
    func glassButton(tint: Color? = nil, covered: Bool = false, radius: CGFloat = 20) -> some View {
        modifier(GlassButton(tint: tint, covered: covered, radius: radius))
    }
}

/// The Always On / covered look: label and stroke in one colour, no fill (2 pt for the primary, 1 pt dim
/// white for secondary controls).
struct OutlineStyle: ButtonStyle {
    let color: Color
    let radius: CGFloat
    let prominent: Bool
    func makeBody(configuration: Configuration) -> some View {
        let shape = RoundedRectangle(cornerRadius: radius)
        configuration.label
            .foregroundStyle(color)
            .background(shape.stroke(prominent ? color : .white.opacity(0.4), lineWidth: prominent ? 2 : 1))
            .contentShape(shape)
    }
}

/// The screen-wide flood of a hold control (G1): which colour rises, how far, and the words over it. One per
/// session screen (`SessionView` draws it over every page); `HoldButton` drives it.
@Observable final class Flood {
    var progress = 0.0
    var color = Color.clear
    var label = Color.white
    var verb = ""
}

/// Hold-to-act control (Terminar, Registrada ✓ un-log; 1 s each). While held, the whole screen floods with
/// `color` rising from the bottom (`FloodOverlay`, G1/G99), a soft `.click` every 0,25 s; at `duration` a firm `.stop`
/// and the action. Release early → drains back in 0,2 s. The hint reads "Mantén…" while held. Its own
/// gesture with a 6 pt movement allowance: a scroll cancels it and can't start it (N15). Reduce Motion, or no
/// flood in the environment (previews): the fill sweeps inside the button instead. Outline, no hold
/// feedback, in Always On or under a dialog, like `GlassButton`.
struct HoldButton: View {
    let title: String
    let hint: String
    /// Word on the flood ("Terminar", "Quitar serie").
    let verb: String
    /// Glass tint and fill.
    let color: Color
    /// Label on the glass, and on the solid fill.
    let label: Color
    let fillLabel: Color
    let duration: TimeInterval
    var covered = false
    var radius: CGFloat = 21
    let action: () -> Void
    @State private var progress = 0.0
    @State private var pressing = false
    @State private var bold = false
    @State private var ticks: Task<Void, Never>?
    @Environment(\.isLuminanceReduced) private var dim
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(Flood.self) private var flood: Flood?

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: radius)
        let outline = dim || covered
        let text = VStack(spacing: -1) {
            Text(title).font(.headline)
            Text(pressing ? "Mantén…" : hint).font(.footnote.weight(bold || pressing ? .heavy : .semibold))
        }
        .lineLimit(1).minimumScaleFactor(0.8)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        text.foregroundStyle(outline ? Theme.stroke(color) : label)
            .overlay {
                text.foregroundStyle(fillLabel).background(color)
                    .mask(alignment: .leading) { GeometryReader { g in Rectangle().frame(width: g.size.width * progress) } }
            }
            .clipShape(shape)
            .background { if outline { shape.stroke(Theme.stroke(color), lineWidth: 2) } }
            .glassEffect(outline ? .identity : .regular.tint(color), in: shape) // not .interactive(): its press effect cancelled the hold inside a List; the fill is the feedback
            .contentShape(shape)
            .onTapGesture {
                bold = true
                Task { try? await Task.sleep(for: .seconds(1.5)); bold = false }
            }
            .onLongPressGesture(minimumDuration: duration, maximumDistance: 6) {
                WKInterfaceDevice.current().play(.stop) // firm: the hold took effect
                release(animated: false)
                action()
            } onPressingChanged: { down in
                if down, !outline { press() } else { release(animated: true) }
            }
    }

    private func press() {
        pressing = true
        let screen = reduceMotion ? nil : flood
        if let screen {
            screen.color = color; screen.label = fillLabel; screen.verb = verb
            // G107: full by 85 % of the hold, so the whole screen is visibly covered before the action fires and clears it.
            withAnimation(.linear(duration: duration * 0.85)) { screen.progress = 1 }
        } else {
            withAnimation(.linear(duration: duration)) { progress = 1 }
        }
        ticks?.cancel()
        ticks = Task {
            for _ in 0..<Int(duration / 0.25) - 1 {
                try? await Task.sleep(for: .seconds(0.25))
                if Task.isCancelled { return }
                WKInterfaceDevice.current().play(.click) // soft tick while filling
            }
        }
    }

    private func release(animated: Bool) {
        ticks?.cancel()
        guard pressing else { return }
        pressing = false
        withAnimation(animated ? .easeOut(duration: 0.2) : nil) {
            progress = 0
            flood?.progress = 0
        }
    }
}

/// The flood itself, over the whole session screen (G1; G99 brings back the bottom-up fill over G19's circle): the
/// content dims and `Flood.color` rises from the bottom edge, every corner covered at 85 % of the hold (G107: at 100 %
/// the action fired and cleared it in the same frame, so full coverage was never seen); the action fires at 100 %.
/// The system clock stays on top: watchOS has no public API to hide it (`.statusBar` is unavailable,
/// `persistentSystemOverlays` and a hidden navigation bar leave it, simulator 2026-10-11). The verb + "Mantén…" sit in the middle, white over the
/// dimmed content and in the label colour inside the fill (accent: white 4.89:1; green: black 10.6:1).
/// Never takes a touch: the finger stays on the button.
struct FloodOverlay: View {
    @Environment(Flood.self) private var flood

    var body: some View {
        let p = flood.progress
        let words = VStack(spacing: 2) {
            Text(flood.verb).font(.title3.weight(.bold))
            Text("Mantén…").font(.headline)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        GeometryReader { g in
            let fill = Rectangle().frame(height: g.size.height * p).frame(maxHeight: .infinity, alignment: .bottom)
            ZStack {
                Color.black.opacity(0.75 * min(p * 3, 1))
                fill.foregroundStyle(flood.color)
                words.foregroundStyle(.white).opacity(p > 0 ? 1 : 0)
                words.foregroundStyle(flood.label).mask { fill }
            }
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// kg or reps value box. The Crown-focused box gets a 2 pt ring in its metric colour; the other a dim
/// 1 pt outline (focus never by colour alone). First tap focuses, second tap opens the keypad.
struct ValueBox: View {
    let field: Field
    /// nil = no kg yet (G69: after a swap): "–", VoiceOver "sin valor".
    let value: Double?
    let focused: Bool
    let tap: () -> Void
    let adjust: (Int) -> Void
    @Environment(\.isLuminanceReduced) private var dim
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let isKg = field == .kg
        let color = isKg ? Theme.kgColor : Theme.repsColor
        let text = value.map { isKg ? Fmt.kg($0) : String(Int($0)) } ?? "–"
        VStack(spacing: -3) {
            // G38 (supersedes G17's slide): the number changes on the detent itself, with a 0,08 s cross-fade at most —
            // nothing moves. Reduce Motion: no fade.
            Text(text)
                .font(.system(size: Metrics.numeral, weight: .semibold, design: .rounded).monospacedDigit())
                .lineLimit(1).minimumScaleFactor(0.8)
                .foregroundStyle(dim ? .white.opacity(0.75) : .white)
                .frame(maxWidth: .infinity)
                .contentTransition(.opacity)
                .animation(reduceMotion ? nil : .linear(duration: 0.08), value: value)
                #if DEBUG
                .onChange(of: value) { _, new in crownLog.debug("box \(new ?? -1)") } // G25: compare with the "detent" line
                #endif
            Text(isKg ? "kg" : "reps").font(.footnote.weight(.bold)).foregroundStyle(color) // labels never dimmed
        }
        .frame(maxWidth: .infinity, minHeight: Metrics.boxHeight, maxHeight: Metrics.boxHeight)
        // Armed (audit #3): a 3 pt ring in the metric colour — the Crown edits this box only while it shows.
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(focused ? color : .white.opacity(0.25), lineWidth: focused ? 3 : 1))
        .contentShape(Rectangle())
        .onTapGesture(perform: tap)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(isKg ? "Peso" : "Repeticiones")
        .accessibilityValue(spoken(text))
        .accessibilityHint(focused ? "Gira la corona para cambiar. Toca otra vez para teclear." : "Toca para editar con la corona.")
        .accessibilityAddTraits(focused ? [.isButton, .isSelected] : .isButton)
        .accessibilityAdjustableAction { dir in adjust(dir == .increment ? 1 : -1) }
        .accessibilityIdentifier(isKg ? "kg" : "reps")
    }
}

extension ValueBox {
    /// "102,5 kilos" · "12 repeticiones" · "sin valor" (an empty kg).
    func spoken(_ text: String) -> String {
        guard value != nil else { return "sin valor" }
        return field == .kg ? "\(text) kilos" : "\(text) repeticiones"
    }
}

/// ‹ / › between the slot's sets. 40 × 30 pt, in the row under the name: far from Hecho and the boxes.
struct NavArrow: View {
    let forward: Bool
    let enabled: Bool
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Image(systemName: forward ? "chevron.right" : "chevron.left")
                .font(.system(size: 16, weight: .bold))
                .frame(width: Metrics.arrowSize.width, height: Metrics.arrowSize.height)
        }
        .glassButton(radius: 14)
        .disabled(!enabled)
        .opacity(enabled ? 1 : 0.3)
        .accessibilityLabel(forward ? "Serie siguiente" : "Serie anterior")
        .accessibilityIdentifier(forward ? "nextSet" : "prevSet")
    }
}

/// The exercise name: one line when it fits (condensed width if needed), else two lines; sentence case
/// from the plan; never truncated at the default text size.
struct SlotName: View {
    let name: String
    var body: some View {
        ViewThatFits(in: .horizontal) {
            Text(name).font(.headline).lineLimit(1).fixedSize()
            Text(name).font(.headline.width(.condensed)).lineLimit(1).fixedSize()
            Text(name).font(.headline).lineLimit(2).minimumScaleFactor(0.85).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityIdentifier("slotName")
    }
}

/// The row beside the clock (top-left). Reserves the clock's width so nothing ever sits under it.
struct Band<Content: View>: View {
    @ViewBuilder let content: Content
    var body: some View {
        HStack(spacing: 5) { content }
            .lineLimit(1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.leading, 12)
            .padding(.trailing, 52)
            .frame(height: 30)
            .padding(.top, 6)
    }
}

/// CAL / FALLO / DROP capsule; nothing for normal sets. Text + colour, black on colour (≥ 6.9:1).
struct TypeBadge: View {
    let type: Session.SetType
    var prefix: String? = nil
    var body: some View {
        if let b = type.badge {
            Text([prefix, b].compactMap { $0 }.joined(separator: " "))
                .font(.footnote.weight(.heavy))
                .foregroundStyle(.black)
                .padding(.horizontal, 5)
                .background(type.color, in: Capsule())
                .fixedSize()
        }
    }
}

/// The special sets of an exercise on Resumen (G2): one badge per set ("S1 FALLO S2 DROP …") when they fit,
/// else one compact chip per type ("F·D·C", "F×2"); VoiceOver always reads the full words.
struct SpecialBadges: View {
    let sets: [Session.SetEntry]
    var body: some View {
        let special = sets.filter { $0.type != .normal }
        let types = [Session.SetType.failure, .dropset, .warmup].filter { t in special.contains { $0.type == t } }
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 3) { ForEach(special, id: \.index) { TypeBadge(type: $0.type, prefix: "S\($0.index + 1)") } }
            HStack(spacing: 3) {
                ForEach(types, id: \.self) { t in
                    let n = special.filter { $0.type == t }.count
                    Text(n > 1 ? "\(t.letter)×\(n)" : t.letter)
                        .font(.footnote.weight(.heavy)).foregroundStyle(.black)
                        .padding(.horizontal, 5)
                        .background(t.color, in: Capsule())
                        .fixedSize()
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(special.map { "serie \($0.index + 1) \($0.type.spanish.lowercased())" }.joined(separator: ", "))
    }
}

/// Sync state: glyph + word + colour, never colour alone.
struct SyncPill: View {
    let state: SyncState
    var body: some View {
        let (glyph, word, color): (String, String, Color) = switch state {
        case .empty: ("icloud", "Sin series", .gray)
        case .pending: ("icloud.and.arrow.up", "Por enviar", Theme.caution)
        case .onPhone: ("iphone", "En el iPhone", Theme.done) // G99: the phone has it (no ✓: "En el iPhone ✓" touched the clock at 42 mm); the server's ack turns it into Enviado ✓
        case .sent: ("icloud.fill", "Enviado ✓", Theme.done)
        case .rejected: ("xmark.icloud", "Rechazada", Theme.missed) // the Worker refused it; details on the phone
        }
        Label(word, systemImage: glyph)
            .font(.footnote.weight(.bold))
            .foregroundStyle(color)
            .labelStyle(.titleAndIcon)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(color.opacity(0.18), in: Capsule())
            .fixedSize()
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("sentState")
    }
}

/// RIR chips 0·1·2·3+, coloured 0 red · 1 orange · 2 yellow · 3+ green (G7), numbers always shown. Selected =
/// solid colour, black number; unselected = clear glass with a 1,5 pt outline in the colour, white number.
/// A tap selects (with a `.click`, in `WatchModel.setRIR`); tapping the selected chip again keeps it. Clearing is
/// only the set menu's "Quitar RIR" (audit #4: a firm press here cleared it silently) or the VoiceOver action.
struct RIRChips: View {
    let selected: Int?
    let set: (Int?) -> Void
    var height: CGFloat = 34
    @Environment(\.isLuminanceReduced) private var dim

    var body: some View {
        GlassEffectContainer(spacing: 4) { HStack(spacing: 4) {
            ForEach(0..<4, id: \.self) { v in
                let on = selected == v
                let color = Theme.rir[v]
                let shape = RoundedRectangle(cornerRadius: height / 2)
                Text(v == 3 ? "3+" : "\(v)")
                    .font(.system(.title3, design: .rounded).weight(.bold))
                    .frame(maxWidth: .infinity, minHeight: height, maxHeight: height)
                    .foregroundStyle(on ? (dim ? color : .black) : .white)
                    .background { // Always On: outlines only (2 pt in the colour for the selected chip)
                        if on && !dim { shape.fill(color) }
                        shape.strokeBorder(dim && !on ? .white.opacity(0.4) : color, lineWidth: on ? 2 : 1.5)
                    }
                    .glassEffect(dim || on ? .identity : .regular.interactive(), in: shape)
                    .contentShape(Rectangle())
                    .onTapGesture { set(v) }
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("RIR \(v == 3 ? "3 o más" : "\(v)")")
                    .accessibilityAddTraits(on ? [.isButton, .isSelected] : .isButton)
                    .accessibilityAction { set(v) }
                    .accessibilityAction(named: "Quitar RIR") { if on { set(nil) } }
                    .accessibilityIdentifier("rir.\(v)")
            }
        } }
        .dynamicTypeSize(...DynamicTypeSize.large)
    }
}

/// −15 / +15 (Hevy pattern), same path as one Crown detent. 40 × 38 pt.
struct RestStep: View {
    let sign: Int
    let adjust: (Int) -> Void
    var body: some View {
        Button { adjust(sign) } label: {
            Text(sign < 0 ? "−15" : "+15").font(.system(.body, design: .rounded).weight(.bold))
                .frame(width: 40, height: 38)
        }
        .glassButton(radius: 19)
        .accessibilityLabel(sign < 0 ? "Quitar 15 segundos" : "Añadir 15 segundos")
        .accessibilityIdentifier(sign < 0 ? "rest.minus" : "rest.plus")
    }
}

/// The "+30 s" chip: time added or removed on this rest. Keeps its size when hidden (no jump).
struct NudgeChip: View {
    let seconds: Int
    var body: some View {
        Text(Fmt.nudge(seconds == 0 ? 15 : seconds))
            .font(.system(.footnote, design: .rounded).weight(.bold).monospacedDigit())
            .foregroundStyle(.black)
            .padding(.horizontal, 6)
            .background(Theme.elapsed, in: Capsule())
            .opacity(seconds == 0 ? 0 : 1)
            .fixedSize()
            .contentTransition(.numericText(value: Double(seconds)))
            .animation(.snappy, value: seconds)
            .accessibilityHidden(seconds == 0)
            .accessibilityLabel("\(seconds) segundos añadidos")
            .accessibilityIdentifier("restNudge")
    }
}

/// Thin draining rest bar (graft from direction D): planned time in yellow, time added beyond the plan in
/// violet (drains first). Hidden wrist-down, so it never shows a stale "full" bar.
struct RestBar: View {
    let start: Date
    let end: Date
    let base: TimeInterval
    @Environment(\.isLuminanceReduced) private var dim

    var body: some View {
        TimelineView(.periodic(from: start, by: 1)) { ctx in
            let total = max(end.timeIntervalSince(start), 1)
            let left = max(end.timeIntervalSince(ctx.date), 0)
            let planned = min(left, base)
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Capsule().fill(.white.opacity(0.18))
                    Capsule().fill(Theme.violet).frame(width: g.size.width * left / total)
                    Capsule().fill(Theme.elapsed).frame(width: g.size.width * planned / total)
                }
                .animation(.linear(duration: 1), value: left)
            }
        }
        .frame(height: 6)
        .opacity(dim ? 0 : 1)
        .accessibilityHidden(true)
    }
}

/// Elapsed session time, system-updated (keeps running and stays cheap in Always On).
struct Elapsed: View {
    let start: Date?
    var body: some View {
        if let start {
            Text(timerInterval: start...Date.distantFuture, countsDown: false)
                .font(.system(.body, design: .rounded).weight(.semibold).monospacedDigit())
                .foregroundStyle(Theme.elapsed)
                .fixedSize()
                .accessibilityLabel("Tiempo de sesión")
        }
    }
}

/// Reads the heart rate itself, so a new reading re-draws only this, never the page around it (G25).
struct Heart: View {
    @Environment(WatchModel.self) private var model
    var body: some View {
        // Re-checked every 5 s so a reading that stops coming turns into "—" (G79, red team MT-05).
        TimelineView(.periodic(from: .now, by: 5)) { ctx in
            let text = model.liveHeartRate(at: ctx.date).map { String(Int($0)) } ?? "—"
            HStack(spacing: 2) {
                Image(systemName: "heart.fill").foregroundStyle(Theme.missed)
                Text(text).monospacedDigit()
            }
            .font(.system(.footnote, design: .rounded).weight(.semibold))
            .fixedSize()
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(text == "—" ? "Sin pulso" : "\(text) pulsaciones")
        }
    }
}

// MARK: - Keypad

/// Full-screen number pad: the typed number on its own line, a 4 × 3 grid, then a full-width OK at the bottom (G74:
/// no corner target for the confirm). Cancel is the sheet's system ✕. Comma only for kg. OK only accepts kg 0–600 /
/// reps 1–100.
struct Keypad: View {
    let field: Field
    /// nil = nothing yet (an empty kg after a swap): "–".
    let current: Double?
    let onDone: (Double?) -> Void
    @State private var text = ""

    private let rows = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], [",", "0", "⌫"]]
    private var value: Double? { Entry.keypad(text, isReps: field == .reps) }
    private var outOfRange: Bool { !text.isEmpty && value == nil && keypadValue(text) != nil }

    var body: some View {
        NavigationStack {
            VStack(spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    Text(text.isEmpty ? current.map { field == .kg ? Fmt.kg($0) : String(Int($0)) } ?? "–" : text)
                        .font(.system(size: 26, weight: .semibold, design: .rounded).monospacedDigit())
                        .foregroundStyle(text.isEmpty ? .secondary : outOfRange ? Theme.caution : .primary)
                    Text(outOfRange ? (field == .kg ? "0–600 kg" : "1–100 reps") : (field == .kg ? "kg" : "reps"))
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(outOfRange ? Theme.caution : .secondary)
                }
                .frame(height: 28)
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("keypadDisplay")
                GlassEffectContainer(spacing: 3) { Grid(horizontalSpacing: 3, verticalSpacing: 3) {
                    ForEach(rows, id: \.self) { row in
                        GridRow {
                            ForEach(row, id: \.self) { key in
                                Button { press(key) } label: {
                                    Text(key).font(.system(size: 20, weight: .semibold, design: .rounded))
                                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                                }
                                .glassButton(radius: 10)
                                .disabled(key == "," && (field != .kg || text.contains(",")))
                                .accessibilityLabel(key == "⌫" ? "Borrar" : key == "," ? "Coma" : key)
                                .accessibilityIdentifier(key)
                            }
                        }
                    }
                } }
                // Accent fill, `onAccent` label: white on magenta, black on the neon lime (G75).
                Button { if let value { onDone(value) } } label: {
                    Label("OK", systemImage: "checkmark").font(.headline)
                        .frame(maxWidth: .infinity, minHeight: 36, maxHeight: 36)
                }
                .glassButton(tint: value == nil ? nil : Theme.accentFill, radius: 18) // off = clear glass, not a dim fill
                .disabled(value == nil)
                .accessibilityIdentifier("keypadOK")
            }
            .padding(.horizontal, 4)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancelar", systemImage: "xmark") { onDone(nil) }.accessibilityIdentifier("keypadCancel")
                }
            }
        }
        .dynamicTypeSize(...DynamicTypeSize.large)
    }

    private func press(_ key: String) {
        switch key {
        case "⌫": if !text.isEmpty { text.removeLast() }
        default: // kg: any value, up to 2 decimals, saved exactly (G14)
            let decimals = text.split(separator: ",", omittingEmptySubsequences: false).dropFirst().first?.count ?? -1
            if text.count < 6, key == "," || decimals < 2 { text += key }
        }
    }
}
