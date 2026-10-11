import Charts
import SwiftUI
import WatchKit
import AthleteCore

// Every Watch screen (design lock, docs/design/DESIGN.md). State and rules live in WatchModel and
// AthleteCore; these views only draw them and route input.

// MARK: - Routine list

struct RoutinePicker: View {
    @Environment(WatchModel.self) private var model

    var body: some View {
        Group {
            if let plan = model.plan {
                List {
                    // G74 (option C): the sync state is the first row, a full-width target clear of the clock and the
                    // top edge (G8); the plan's check time is its own line inside it, never merged (SY-01).
                    SyncRow()
                    if let last = model.lastSession {
                        Text("Última: \(last.routineTitle) · \(Fmt.dayTime(last.startedAt))").foregroundStyle(.secondary)
                            .font(.footnote)
                            .listRowBackground(Color.clear)
                            .accessibilityIdentifier("lastSession")
                    }
                    if model.gyms.multi, model.gyms.list.count > 1, let gym = model.gyms.name(model.nextGym) {
                        NavigationLink { GymPicker() } label: { // G92: pre-filled, one tap to change, never a question
                            LabeledContent("Gimnasio", value: gym).font(.footnote)
                        }
                        .accessibilityIdentifier("gym")
                    }
                    // G40: the suggestion first (today's calendar routine, else the one after the last session in the
                    // rotation), then the rotation from there. Any routine can still be picked.
                    let last = model.lastSession
                    let suggested = plan.suggestedRoutine(lastTitle: last?.routineTitle, lastDay: last.map { Plan.day($0.startedAt) })
                    ForEach(plan.routineKeys(lastTitle: last?.routineTitle, lastDay: last.map { Plan.day($0.startedAt) }), id: \.self) { key in
                        let r = plan.routines[key]!
                        Button { model.beginCountdown(routineKey: key) } label: {
                            VStack(alignment: .leading, spacing: 1) {
                                if let suggested, suggested.key == key { // text + glyph + colour, never colour alone
                                    Label(suggested.today ? "Hoy en el plan" : "Siguiente en la rotación", systemImage: "arrow.clockwise")
                                        .font(.footnote.weight(.bold)).foregroundStyle(Theme.elapsed)
                                        .lineLimit(1).minimumScaleFactor(0.8)
                                        .accessibilityIdentifier("suggested")
                                }
                                Text(r.title).font(.headline)
                                Text(Fmt.routine(r.slots.count, r.slots.reduce(0) { $0 + plan.setCount($1) }))
                                    .font(.footnote).foregroundStyle(.secondary)
                            }
                            .padding(.vertical, 2)
                        }
                        .accessibilityIdentifier("routine.\(key)")
                    }
                    Text(Bundle.main.versionLabel).font(.footnote).foregroundStyle(.secondary)
                        .listRowBackground(Color.clear)
                }
                .navigationTitle("Rutinas")
            } else {
                ScrollView {
                    VStack(spacing: 10) {
                        SyncRow() // option C works here too: unconfirmed sessions can exist without a plan
                        Text("Abre Athlete OS en el iPhone para recibir el plan.").multilineTextAlignment(.center)
                        Text(Bundle.main.versionLabel).font(.footnote).foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 4)
                }
            }
        }
        .demoDimmed() // reaches the status row too (-demoDimmed shot of its Always On outline)
        .onAppear { model.autoSync() } // at most every 15 min, only with the phone in range; no effect on screen
    }
}

/// The next session's gym (G92), from the phone's list. Picking one goes back to the routines.
struct GymPicker: View {
    @Environment(WatchModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        List(model.gyms.list) { gym in
            Button {
                model.pickedGym = gym.id
                dismiss()
            } label: {
                Label { Text(gym.name) } icon: { if gym.id == model.nextGym { Image(systemName: "checkmark") } }
            }
            .accessibilityAddTraits(gym.id == model.nextGym ? .isSelected : [])
        }
        .navigationTitle("Gimnasio")
    }
}

/// "Plan comprobado hoy 07:12" (G51): when the phone last checked the server for the plan. Amber with a clock glyph
/// after 8 days (text + glyph + colour). Re-drawn every minute, so "hoy" never goes stale across midnight (SY-15).
struct PlanLine: View {
    @Environment(WatchModel.self) private var model

    var body: some View {
        TimelineView(.everyMinute) { ctx in
            let line = SyncText.planLine(checked: model.planCheckedAt, now: ctx.date)
            Label {
                Text(line.text).fixedSize(horizontal: false, vertical: true) // wraps under large type, never truncates
            } icon: {
                if line.stale { Image(systemName: "clock.badge.exclamationmark") }
            }
            .labelStyle(StaleLabel(stale: line.stale))
            .foregroundStyle(line.stale ? Theme.caution : .secondary)
            .accessibilityIdentifier("planLine")
        }
    }
}

/// Icon only when there is one (the fresh plan line is text alone, aligned with "Última").
private struct StaleLabel: LabelStyle {
    let stale: Bool
    func makeBody(configuration: Configuration) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            if stale { configuration.icon }
            configuration.title
        }
    }
}

/// G74 status row (option C of `docs/design/sync/`, replacing G51's corner button): full-width clear glass —
/// the sessions' glyph (✓ Al día · ↑ n sin confirmar · ! rechazada / ilegible), the state in words, the plan line
/// under it, and a chevron. Tap → the details sheet. The glyph spins only while a sync the athlete asked for is out;
/// otherwise only a symbol replace on a change. No effects with Reduce Motion or the wrist down, no haptics.
struct SyncRow: View {
    @Environment(WatchModel.self) private var model
    @Environment(\.isLuminanceReduced) private var dimmed
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var open = false

    var body: some View {
        let status = model.syncStatus
        let spinning = model.syncing && model.syncManual
        let look = SyncLook(status)
        Button { open = true } label: {
            HStack(spacing: 6) {
                Image(systemName: spinning ? "arrow.triangle.2.circlepath" : look.symbol)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(spinning ? .white : look.color)
                    .contentTransition(.symbolEffect(.replace))
                    .symbolEffect(.rotate, isActive: spinning)
                    .symbolEffectsRemoved(reduceMotion || dimmed)
                    .frame(width: 24)
                VStack(alignment: .leading, spacing: 0) {
                    Text(status.short).font(.subheadline.weight(.semibold)) // "12 sin confirmar" fits one line at 42 mm
                        .foregroundStyle(status == .upToDate ? Color.white : look.color)
                        .fixedSize(horizontal: false, vertical: true)
                    PlanLine().font(.footnote)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right").font(.footnote.weight(.bold)).foregroundStyle(.secondary)
            }
            .padding(.horizontal, 8).padding(.vertical, 6)
            .frame(maxWidth: .infinity, minHeight: 48)
        }
        .glassButton(radius: 16)
        .listRowBackground(Color.clear)
        .listRowInsets(EdgeInsets())
        .accessibilityLabel("Sincronización") // replaces the children's words; the button keeps its action
        .accessibilityValue("\(status.sentence). \(SyncText.planLine(checked: model.planCheckedAt, now: .now).text)")
        .accessibilityHint("Muestra los detalles")
        .accessibilityIdentifier("syncRow")
        .sheet(isPresented: $open, onDismiss: { model.syncResult = nil }) { SyncSheet() } // the result lasts while it's open
    }
}

/// Symbol and colour per state (distinct silhouettes, never colour alone). ✓ uses `done`: green, white in Neón verde.
struct SyncLook {
    let symbol: String
    let color: Color

    init(_ status: SyncStatus) {
        switch status {
        case .upToDate: (symbol, color) = ("checkmark.icloud", Theme.done)
        case .unconfirmed: (symbol, color) = ("icloud.and.arrow.up", Theme.caution)
        case .problem: (symbol, color) = ("exclamationmark.icloud", Theme.missed)
        }
    }
}

/// Details (G51): state, plan checked + published, each unconfirmed / refused session, unreadable files, and
/// "Sincronizar ahora" (never disabled for reachability; disabled only while a request is out) with its result.
struct SyncSheet: View {
    @Environment(WatchModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var confirmRestart = false

    var body: some View {
        let status = model.syncStatus
        let look = SyncLook(status)
        NavigationStack {
            List {
                Label(status.sentence, systemImage: look.symbol)
                    .font(.headline).foregroundStyle(look.color)
                    .listRowBackground(Color.clear)
                    .accessibilityIdentifier("syncState")
                Section("Plan") {
                    PlanLine().font(.body)
                    if let day = SyncText.published(model.planPublishedAt) { Text("Publicado \(day)") }
                }
                let waiting = model.stored.filter { model.acks.isProblem($0) || !model.acks.unsent([$0]).isEmpty }
                    .sorted { $0.startedAt > $1.startedAt }
                if !waiting.isEmpty || model.unreadable > 0 {
                    Section("Sesiones") {
                        ForEach(waiting) { s in
                            VStack(alignment: .leading, spacing: 1) {
                                Text("\(s.routineTitle) · \(SyncText.when(s.startedAt, now: .now))")
                                if model.acks.isProblem(s) {
                                    Text("Rechazada · el motivo está en el iPhone").foregroundStyle(Theme.missed)
                                } else {
                                    Text("Sin confirmar").foregroundStyle(Theme.caution)
                                }
                            }
                            .font(.footnote)
                            .accessibilityElement(children: .combine)
                        }
                        if model.unreadable > 0 {
                            Text(model.unreadable == 1 ? "1 archivo de sesión ilegible en el reloj"
                                 : "\(model.unreadable) archivos de sesión ilegibles en el reloj")
                                .font(.footnote).foregroundStyle(Theme.missed)
                        }
                    }
                }
                Section {
                    let spinning = model.syncing && model.syncManual
                    Button { model.syncNow() } label: {
                        Label(model.syncing ? "Sincronizando…" : "Sincronizar ahora", systemImage: "arrow.triangle.2.circlepath")
                            .symbolEffect(.rotate, isActive: spinning)
                            .symbolEffectsRemoved(reduceMotion)
                            .font(.headline).frame(maxWidth: .infinity, minHeight: 44)
                    }
                    .glassButton(radius: 22)
                    // One request at a time, never blocked for reachability (SY-06). Not `.disabled`: its 30 % label would
                    // make "Sincronizando…" unreadable; a tap while out is ignored (and `syncNow` only joins it anyway).
                    .allowsHitTesting(!model.syncing)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets())
                    .accessibilityIdentifier("syncNow")
                } footer: {
                    if let result = model.syncResult {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(result.text).foregroundStyle(result == .ok ? Theme.done : Theme.caution)
                            if result == .watchNotSeen { ForEach(SyncResult.g44Steps, id: \.self) { Text($0) } }
                        }
                        .font(.footnote)
                        .accessibilityIdentifier("syncResult")
                    } else if !model.syncing {
                        Text("Envía lo pendiente y pide el plan al iPhone.").font(.footnote)
                    }
                }
                if model.session == nil { // G98c: hidden while a session runs (it reloads the session files)
                    Section {
                        Button { confirmRestart = true } label: {
                            Label("Reiniciar conexión", systemImage: "arrow.clockwise")
                                .font(.headline).frame(maxWidth: .infinity, minHeight: 44)
                        }
                        .glassButton(radius: 22)
                        .allowsHitTesting(!model.syncing)
                        .listRowBackground(Color.clear)
                        .listRowInsets(EdgeInsets())
                        .accessibilityIdentifier("restartConnection")
                    } footer: {
                        // A reinstall over the app keeps its files; deleting the Watch app first loses unconfirmed sessions (G44 copy).
                        Text("Si nada llega: reactiva la conexión, reenvía lo pendiente, recarga el reloj y sincroniza. No borra nada. Si el iPhone dice que la app del reloj no está instalada, esto no lo arregla: reinstala las dos apps desde el Mac, sin borrarlas antes (borrarlas pierde lo no enviado).")
                            .font(.footnote)
                    }
                }
            }
            .navigationTitle("Sincronización")
            .confirmationDialog("¿Reiniciar conexión?", isPresented: $confirmRestart, titleVisibility: .visible) {
                Button("Cancelar", role: .cancel) {} // the safe choice first
                Button("Reiniciar") { model.restartConnection() }
            } message: {
                Text("Reactiva la conexión con el iPhone, reenvía las sesiones sin confirmar y sincroniza. No borra nada.")
            }
        }
    }
}

// MARK: - Session pages

enum Page: Hashable { case overview, set, metrics, music }

/// A running session: Apple Workout's page order, Resumen/controls ← Set (home) → Métricas → Música (L10).
/// No page has a navigation title or toolbar, so swiping never re-lays out the clock area.
struct SessionView: View {
    @Environment(WatchModel.self) private var model
    @Environment(\.isLuminanceReduced) private var envDimmed
    @Environment(\.scenePhase) private var scenePhase
    @State private var page = Page.set
    @State private var flood = Flood()

    private var dimmed: Bool {
        #if DEBUG
        if Demo.dimmed { return true }
        #endif
        return envDimmed
    }

    var body: some View {
        @Bindable var model = model
        TabView(selection: $page) {
            OverviewPage { page = .set }.demoDimmed().tag(Page.overview)
            // Any alert or dialog up: the Set page is not in front, so Double Tap does nothing (N5).
            SetPage(isFront: page == .set && !model.askFinish).demoDimmed().tag(Page.set)
            MetricsPage(isFront: page == .metrics).demoDimmed().tag(Page.metrics) // no Double Tap target here (G79)
            NowPlayingView().tag(Page.music)
        }
        .tabViewStyle(PageTabViewStyle(indexDisplayMode: dimmed ? .never : .automatic)) // `.page(...)` hides the dots in the simulator but draws pages ~20 pt wider than the screen
        .overlay { FloodOverlay() } // G1: a hold (Terminar, un-log) floods the whole screen
        .environment(flood)
        #if DEBUG
        .onAppear { if Demo.flood { flood.color = Theme.accentFill; flood.verb = "Terminar"; flood.progress = 0.6 } }
        #endif
        // Rest end never moves the page (must-fix 8). Wrist down → back to the live set, like Workout (N1) —
        // except on Métricas, a glance page made for Always On (L10); Double Tap does nothing there.
        // Métricas stays, but back on its first view (G79): one Always On layout, and a ghost Crown turn never leaves
        // him on Zonas or Pulso.
        .onChange(of: dimmed) { _, d in if d { if page != .metrics { page = .set }; model.metricsView = 0; model.backToLive() } }
        .onChange(of: scenePhase) { _, p in if p != .active { model.backToLive() } }
        .onChange(of: page) { _, p in
            model.nav.disarm() // a page change disarms the Crown (audit #3)
            if p == .set { model.flip() } // arriving on Set: 1 s touch lockout
        }
        .onChange(of: model.showFinish) { _, show in if show { page = .overview } } // last planned set + rest done (G22)
        .alert("¿Has terminado?", isPresented: $model.askFinish) {
            Button("Seguir") { model.keepGoing() } // the safe choice first
            // Never finishes in one tap: goes to Overview, where Terminar is hold + confirm (RT-16).
            Button("Terminar") { model.keepGoing(); page = .overview }
        } message: {
            Text("Llevas 20 minutos sin registrar series.")
        }
    }
}

/// The Set page: the set and the rest timer stacked and cross-faded (never swapped), one Crown for both.
/// Every Crown detent is one step: 2,5 kg on a barbell / 1,25 kg otherwise (on the step grid), 1 rep or 15 s.
/// Low sensitivity everywhere (G18). kg/reps move only while a value box is armed by a tap (audit #3). Unarmed and
/// not resting, the page is not focusable at all, so the Crown has nothing to drive and no detent clicks (G26).
struct SetPage: View {
    let isFront: Bool
    @Environment(WatchModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var typing: Field?
    /// The set the keypad or menu was opened on (nil = live): a value lands only there, even if the Watch
    /// went back to the live set meanwhile (wrist-down, N1).
    @State private var openedOn: Int?
    @State private var menu = false
    @State private var changing = false
    /// "⇄ Cambiar ejercicio" picked in the set menu: the picker opens once the menu is gone (G69).
    @State private var wantSwap = false
    @State private var swapping = false
    @State private var crown = CrownTicks()
    @FocusState private var crownFocus: Bool

    private var resting: Bool { model.restEnd != nil }
    /// The Crown drives something: the rest timer, or the armed value box (G26).
    private var crownLive: Bool { resting || model.nav.crownEdits }
    /// Only while the page is in front (G79, red team MT-07): off-screen it must never keep the Crown, or a turn on
    /// Métricas would move the rest ±15 s unseen.
    private var crownOwned: Bool { crownLive && isFront }
    private var covered: Bool { typing != nil || menu || changing || swapping }
    /// The 1 s lockout after a flip (re-evaluated when `lockTick` changes).
    private var touchOK: Bool { _ = model.lockTick; return model.lockout.allowsTouch(at: .now) }

    var body: some View {
        ZStack(alignment: .top) {
            SetLayer(doubleTap: DoubleTap.logsSet(front: isFront, resting: resting, covered: covered, touchOK: touchOK,
                                                  proposed: model.autoPicked),
                     covered: covered,
                     openKeypad: { openedOn = model.nav.editing; typing = $0 },
                     openMenu: { openedOn = model.nav.editing; menu = true })
                .opacity(resting ? 0 : 1)
                .allowsHitTesting(!resting && touchOK)
                .accessibilityHidden(resting)
            // The RIR chips can't log a set, so they skip the 1 s lockout (audit #4); the controls keep it.
            RestLayer(isFront: isFront && resting && !covered && touchOK, touchOK: touchOK, change: { changing = true })
                .opacity(resting ? 1 : 0)
                .allowsHitTesting(resting)
                .accessibilityHidden(!resting)
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.2), value: resting)
        .sessionPage()
        .dynamicTypeSize(...DynamicTypeSize.xLarge) // fixed layout: capped (lists elsewhere scale fully)
        .focusable(crownOwned) // G26: unarmed, nothing on the page takes the Crown, so it never clicks
        .focused($crownFocus)
        .focusEffectDisabled()
        // G25: each notch steps the model straight from the binding's setter. The tick count lives in a plain
        // class, so a notch doesn't re-render this whole page (rest layer, sheets): only what reads the draft.
        .digitalCrownRotation(detent: Binding(get: { crown.ticks }, set: { crown.turn(to: $0, model.step) }),
                              from: -100_000, through: 100_000, by: 1,
                              sensitivity: .low, isContinuous: false,
                              isHapticFeedbackEnabled: crownOwned,
                              onIdle: model.crownSettled)
        .onAppear { crownFocus = crownOwned; model.syncDraft() }
        .onChange(of: crownOwned) { crownFocus = crownOwned } // also gives the Crown up when the page leaves the front
        .onChange(of: covered) { if !covered { crownFocus = crownOwned } }
        .sheet(item: $typing) { f in
            let shown = model.viewedSet
            Keypad(field: f, current: f == .kg ? (shown?.weightKg ?? model.kg) : Double(shown?.reps ?? model.reps)) { value in
                if let value, openedOn == model.nav.editing { model.typed(value, field: f) }
                typing = nil
            }
            .presentationBackground(.black)
        }
        .sheet(isPresented: $changing) {
            ChangeNextSheet { changing = false }.presentationBackground(.black)
        }
        .sheet(isPresented: $menu, onDismiss: { if wantSwap { wantSwap = false; swapping = true } }) {
            let live = openedOn == nil && model.nav.isLive // slot-level rows only on the live set (panel must-fix 14)
            SetMenu(title: menuTitle,
                    addSet: model.nav.isLive ? model.currentSlot.map { key in { model.addSet(slotKey: key) } } : nil,
                    clearRIR: clearRIR,
                    warmup: live && model.canReopenWarmup ? { model.reopenWarmup() } : nil,
                    swap: live && model.canSwap ? { wantSwap = true } : nil,
                    swapBack: live && model.canSwap && model.currentInUse?.substituted == true
                        ? (model.currentPlanSlot?.short ?? "", { model.swapBack() }) : nil) { t in
                if openedOn == model.nav.editing { model.setType(t) }
            }
            .presentationBackground(.black)
        }
        .sheet(isPresented: $swapping) {
            SwapSheet { swapping = false }.presentationBackground(.black)
        }
    }

    /// "Quitar RIR" on a logged set that has one: the only way to clear a RIR (audit #4).
    private var clearRIR: (() -> Void)? {
        guard let e = model.nav.editing, let key = model.currentSlot, model.viewedSet?.rir != nil else { return nil }
        return { if openedOn == e { model.setRIR(nil, slot: key, index: e) } }
    }

    /// "Serie 2 · Normal": the set on screen, which is the one the menu changes.
    private var menuTitle: String {
        guard let n = model.shownSetNumber, !model.showsWarmup else { return "Calentamiento" }
        return "Serie \(n) · \((model.viewedSet?.type ?? model.type).spanish)"
    }
}

/// The Crown's detent count, outside SwiftUI's state so a notch re-renders nothing by itself (G25).
final class CrownTicks {
    private(set) var ticks = 0.0

    func turn(to new: Double, _ step: (Int, Field?) -> Void) {
        let d = Int((new - ticks).rounded())
        ticks = new
        step(d, nil)
    }
}

/// Long-press set menu (G20): each type in its badge colour with a black label (CAL 11.5:1, FALLO 6.04:1,
/// DROP 7.72:1); Normal and "+1 serie" on clear glass, white. The sheet's system ✕ closes it unchanged.
struct SetMenu: View {
    let title: String
    let addSet: (() -> Void)?
    var clearRIR: (() -> Void)? = nil
    /// "↶ Calentamiento": reopens the warm-up guide (G67) until a working set is logged.
    var warmup: (() -> Void)? = nil
    /// "⇄ Cambiar ejercicio" and "↶ Volver a {short}" (G69), under their own "Ejercicio" label, last.
    var swap: (() -> Void)? = nil
    var swapBack: (String, () -> Void)? = nil
    let pick: (Session.SetType) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                Text(title).font(.headline).frame(maxWidth: .infinity, alignment: .leading)
                if let addSet { row("+1 serie", fill: nil) { addSet() } }
                if let warmup { row("↶ Calentamiento", fill: nil, id: "reopenWarmup") { warmup() } }
                ForEach([Session.SetType.warmup, .normal, .failure, .dropset], id: \.self) { t in
                    row(t.spanish, fill: t == .normal ? nil : t.color) { pick(t) }
                }
                if let clearRIR { row("Quitar RIR", fill: nil) { clearRIR() } } // last: away from the types
                if swap != nil || swapBack != nil { // a slot-level action, apart from the set's own rows
                    Text("Ejercicio").font(.footnote.weight(.bold)).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 6)
                    if let swap { row("⇄ Cambiar ejercicio", fill: nil, id: "swapExercise") { swap() } }
                    if let back = swapBack {
                        row("↶ Volver a \(back.0)", fill: nil, id: "swapBack") { back.1() }
                    }
                }
            }
            .padding(.horizontal, 4)
        }
    }

    private func row(_ word: String, fill: Color?, id: String? = nil, action: @escaping () -> Void) -> some View {
        Button { action(); dismiss() } label: {
            Text(word).font(.body.weight(.semibold)).multilineTextAlignment(.center)
                .foregroundStyle(fill == nil ? .white : .black)
                .frame(maxWidth: .infinity, minHeight: 44)
                .background(fill ?? .clear, in: RoundedRectangle(cornerRadius: 22))
                .contentShape(RoundedRectangle(cornerRadius: 22))
        }
        .buttonStyle(.plain)
        .glassEffect(fill == nil ? .regular.interactive() : .identity, in: RoundedRectangle(cornerRadius: 22))
        .accessibilityIdentifier(id ?? word)
    }
}

/// What the set half of the Set page draws: the live set, a logged set (‹ / ›), or "Completado".
struct SetLayer: View {
    /// Hecho may take the Double Tap (`DoubleTap.logsSet`).
    let doubleTap: Bool
    let covered: Bool
    let openKeypad: (Field) -> Void
    let openMenu: () -> Void
    @Environment(WatchModel.self) private var model

    var body: some View {
        if let key = model.currentSlot, let slot = model.plan?.slots[key] {
            VStack(spacing: 0) {
                Band {
                    Elapsed(start: model.session?.startedAt)
                    Heart() // reads the heart rate itself: a new reading re-draws only it, not the set (G25)
                }
                if model.showsWarmup { // G67: the read-only ramp before Serie 1, in the Set page's own frame
                    WarmupCard(doubleTap: doubleTap, covered: covered)
                        .contentShape(Rectangle())
                        .onLongPressGesture(minimumDuration: 0.6) { openMenu() } // "⇄ Cambiar ejercicio" before the ramp too
                } else {
                    let use = slot.inUse(model.session?.currentExercise(forSlot: key))
                    ViewThatFits(in: .vertical) { // long names take two lines; then the line above the boxes goes
                        content(slot: slot, key: key, full: true, name: use.name)
                        // Q26: the coach's short name keeps the set line (and the "🔗 partner" line, G39) when the full name takes two lines
                        if use.short != use.name { content(slot: slot, key: key, full: true, name: use.short) }
                        content(slot: slot, key: key, full: false, name: use.name)
                    }
                }
            }
            .padding(.horizontal, Metrics.sidePadding)
            .padding(.bottom, Metrics.dotsClearance)
        } else {
            Text("Elige un ejercicio en Resumen.").multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder private func content(slot: Plan.Slot, key: String, full: Bool, name: String) -> some View {
        let done = model.confirmedInSlot
        let total = slot.plannedSets.count + (model.addedSets[key] ?? 0)
        let logged = model.viewedSet
        let completed = logged == nil && model.livePrefill == nil
        VStack(spacing: 0) {
            VStack(spacing: 0) {
                SlotName(name: name).accessibilityLabel(model.currentInUse?.name ?? name)
                navRow(done: done, total: total, logged: logged, completed: completed)
                if completed {
                    completedList(done)
                } else {
                    if full { lineAbove(slot: slot, done: done, logged: logged) }
                    HStack(spacing: 5) {
                        box(.kg, logged.map(\.weightKg) ?? model.kg).frame(width: 100)
                        box(.reps, Double(logged?.reps ?? model.reps))
                    }
                    .geometryGroup()
                    if let logged, let e = model.nav.editing { // set or change its RIR any time (audit #5 / N12)
                        RIRChips(selected: logged.rir, set: { model.setRIR($0, slot: key, index: e) }, height: 34)
                            .padding(.top, 4)
                    } else {
                        lineBelow(slot: slot, done: done, logged: logged)
                    }
                }
            }
            .contentShape(Rectangle())
            .onLongPressGesture(minimumDuration: 0.6) { if !completed { openMenu() } } // never on Hecho (motion J10)
            Spacer(minLength: 0)
            mainButton(key: key, logged: logged, completed: completed)
        }
    }

    // ‹ Serie 2/3 ›  (short form "S2/3" when a badge rides along)
    private func navRow(done: [Session.SetEntry], total: Int, logged: Session.SetEntry?, completed: Bool) -> some View {
        let n = model.shownSetNumber
        let type = logged?.type ?? (completed ? .normal : model.type)
        return HStack(spacing: 4) {
            NavArrow(forward: false, enabled: model.nav.canGoBack(confirmed: done.count)) { model.back() }
            Group {
                if completed {
                    Text("Completado").foregroundStyle(Theme.done)
                } else if let n, type.badge != nil {
                    HStack(spacing: 4) { Text("S\(n)/\(total)"); TypeBadge(type: type) }
                } else if n == nil { // a warm-up counts for nothing: no set number (N7)
                    HStack(spacing: 4) { Text("Calent."); TypeBadge(type: .warmup) }
                } else {
                    Text("Serie \(n ?? 0)/\(total)")
                }
            }
            .font(.headline).monospacedDigit().lineLimit(1).minimumScaleFactor(0.8)
            .frame(maxWidth: .infinity)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("setPosition")
            NavArrow(forward: true, enabled: model.nav.canGoForward) { model.forward() }
        }
        .frame(height: Metrics.arrowSize.height)
    }

    /// Live set 1: "Últ. 97,5 × 12" (last session's top set). Later sets: the set just done "✓ 102,5 × 12"
    /// with its badge. Logged set: when it was done and its RIR.
    @ViewBuilder private func lineAbove(slot: Plan.Slot, done: [Session.SetEntry], logged: Session.SetEntry?) -> some View {
        HStack(spacing: 4) {
            if let logged {
                Text("Hecha \(Fmt.time(logged.doneAt)) · RIR \(logged.rir.map(Fmt.rir) ?? "—")")
            } else if let p = model.plates, let kg = model.kg,
                      (model.nav.crownEdits && model.field == .kg) || model.platesAfterRamp {
                // G68: the plates for the live kg while kg is armed (every detent, from the in-memory draft, G25), and
                // on set 1 after the ramp. Never on a logged set (its RIR line keeps its place).
                PlateLine(total: kg, start: p.start, sides: p.sides)
            } else if let partner = model.supersetPartner { // G39/G55: "🔗 Curl inclinado" — the link glyph says superset
                Image(systemName: "link").foregroundStyle(Theme.elapsed)
                Text(partner).foregroundStyle(Theme.elapsed).truncationMode(.tail)
                    .accessibilityLabel("Superserie con \(model.supersetPartnerInUse?.name ?? partner)")
            } else if model.currentInUse?.substituted == true, done.isEmpty {
                Text(" ") // a substitute has no last session here: nothing, rather than the planned exercise's "Últ."
            } else if let prev = done.last {
                Image(systemName: "checkmark").foregroundStyle(Theme.done).accessibilityLabel("Serie anterior")
                Text(Fmt.set(prev.weightKg, prev.reps)).monospacedDigit()
                TypeBadge(type: prev.type)
                if let rir = prev.rir { Text("· RIR \(Fmt.rir(rir))").monospacedDigit() } // a recorded RIR always shows (audit #2)
            } else {
                Text(slot.history?.first.map { "Últ. \(Fmt.top($0.top))" } ?? "Sin sesión anterior")
            }
        }
        .font(.body).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.75)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("lineAbove")
    }

    /// "Obj 100 × 12-12-10" with this set's reps in white — the coach's target and the sets to come.
    /// A barbell weight the gym's plates can't make replaces it: "No cargable · +0,62/lado" (L3, non-blocking).
    @ViewBuilder private func lineBelow(slot: Plan.Slot, done: [Session.SetEntry], logged: Session.SetEntry?) -> some View {
        let kg = logged?.weightKg ?? model.kg
        let index = (model.shownSetNumber ?? 0) - 1 // a warm-up bolds nothing
        Group {
            if let use = model.currentInUse, use.substituted { // G69: the target is the planned exercise's, not this one's
                Text("⇄ En vez de \(slot.short)").foregroundStyle(Theme.elapsed).minimumScaleFactor(0.65) // never cut mid-word (#10)
                    .accessibilityLabel("Cambiado: \(use.name), en vez de \(slot.name)")
                    .accessibilityIdentifier("swapLine")
            } else if let kg, kg != model.typedKg, let p = model.loadStart, // quiet once typed (G14)
                      let r = PlateMath.unloadablePerSide(total: kg, startWeight: p.start, sides: p.sides) {
                Text("No cargable · +\(Fmt.perSide(r))\(p.sides == 1 ? " kg" : "/lado")")
                    .foregroundStyle(Theme.caution).accessibilityIdentifier("unloadable")
            } else if let t = slot.target, !t.repsList.isEmpty {
                ladder(kg: t.kg, reps: t.repsList, current: index)
            } else {
                Text("Sin objetivo").foregroundStyle(.secondary)
            }
        }
        .font(.body).lineLimit(1).minimumScaleFactor(0.8)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func ladder(kg: Double, reps: [Int], current: Int) -> some View {
        var t = Text("Obj \(Fmt.kg(kg)) × ").foregroundStyle(.secondary)
        for (i, r) in reps.enumerated() {
            let dash = i > 0 ? Text("-").foregroundStyle(.secondary) : Text("")
            let rep = i == current ? Text("\(r)").foregroundStyle(.white).bold() : Text("\(r)").foregroundStyle(.secondary)
            t = Text("\(t)\(dash)\(rep)")
        }
        return t.monospacedDigit()
            .accessibilityLabel("Objetivo \(Fmt.kg(kg)) kilos, \(reps.map(String.init).joined(separator: ", ")) repeticiones")
    }

    /// Every set of the finished exercise; scrolls when they don't fit (G3). Nothing here takes input.
    private func completedList(_ done: [Session.SetEntry]) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 1) {
                ForEach(done, id: \.index) { s in
                    HStack(spacing: 4) {
                        Text("S\(s.index + 1)").foregroundStyle(.secondary)
                        Text(Fmt.set(s.weightKg, s.reps)).monospacedDigit()
                        TypeBadge(type: s.type)
                    }
                }
            }
            .font(.body)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .scrollBounceBehavior(.basedOnSize)
        .accessibilityIdentifier("completedList")
    }

    private func box(_ f: Field, _ v: Double?) -> some View {
        // On a past set the ring shows only once a box was tapped there: that is when the Crown edits it (N2).
        ValueBox(field: f, value: v, focused: model.field == f && model.nav.crownEdits,
                 tap: { if model.tapBox(f) { openKeypad(f) } }, // second tap → keypad
                 adjust: { model.step($0, field: f) })
    }

    /// One spot, four states: Hecho (accent) · Registrada ✓ (green, un-logs on touch) · Deshacer (4 s) ·
    /// +1 serie (slot done).
    @ViewBuilder private func mainButton(key: String, logged: Session.SetEntry?, completed: Bool) -> some View {
        Group {
            if model.undo.item != nil {
                Button { model.restoreUnlogged() } label: {
                    Label("Deshacer", systemImage: "arrow.uturn.backward").font(.headline)
                        .frame(maxWidth: .infinity, minHeight: Metrics.primaryHeight)
                }
                .glassButton(covered: covered, radius: 21)
                .accessibilityIdentifier("undo")
            } else if logged != nil {
                UnlogButton(covered: covered) { model.unlog() } // no Double Tap here: it never un-logs
            } else if let cap = model.cap(key) { // contract caps (audit #8): say why, log nothing
                Text(cap == .sets ? "Máx. \(Session.maxSets) series" : "Máx. \(Session.maxExercises) ejercicios")
                    .font(.headline).foregroundStyle(Theme.caution)
                    .frame(maxWidth: .infinity, minHeight: Metrics.primaryHeight)
                    .accessibilityIdentifier("capReached")
            } else if !completed, model.kg == nil {
                // G69: no kg after a swap — "Pon el peso" opens the kg keypad; Hecho and Double Tap wait for a kg.
                Button { openKeypad(.kg) } label: {
                    Text("Pon el peso").font(.headline).frame(maxWidth: .infinity, minHeight: Metrics.primaryHeight)
                }
                .glassButton(covered: covered, radius: 21)
                .accessibilityHint("Abre el teclado del peso.")
                .accessibilityIdentifier("setWeight")
            } else if completed {
                Button { model.addSet(slotKey: key) } label: {
                    Label("+1 serie", systemImage: "plus").font(.headline)
                        .frame(maxWidth: .infinity, minHeight: Metrics.primaryHeight)
                }
                .glassButton(covered: covered, radius: 21)
                .accessibilityIdentifier("addSet")
            } else {
                Button { model.confirm() } label: {
                    Text("Hecho").font(.title3.weight(.bold)).frame(maxWidth: .infinity, minHeight: Metrics.primaryHeight)
                }
                .glassButton(tint: Theme.accentFill, covered: covered, radius: 21)
                .disabled(model.plan?.slots[key]?.templateId == nil)
                // Double Tap = Hecho only on the live set, never on a slot the Watch proposed until it is touched.
                .handGestureShortcut(.primaryAction, isEnabled: doubleTap)
                .accessibilityIdentifier("done")
            }
        }
        .frame(height: Metrics.primaryHeight)
    }
}

/// G67 (option D, read-only): the coach's ramp for the live first working kg — every step's kg × reps and, on a
/// plate-loaded slot, its plates — before Serie 1, in the Set page's own frame (the page order never changes).
/// Nothing here logs or touches the draft: "Empezar series" (the Double Tap target, same gates as Hecho) closes it,
/// with the 1 s lockout. No Crown here. More steps than fit scroll (`lean:` until a slot has more than 3).
struct WarmupCard: View {
    let doubleTap: Bool
    let covered: Bool
    @Environment(WatchModel.self) private var model

    var body: some View {
        let ramp = model.ramp
        let use = model.currentInUse
        VStack(alignment: .leading, spacing: 0) {
            Text("Calentamiento").font(.headline).foregroundStyle(Theme.caution)
                .frame(height: Metrics.arrowSize.height)
                .accessibilityIdentifier("warmupTitle")
            Text("\(use?.short ?? "") · \(Fmt.set(model.kg, model.reps))") // the first working set the ramp leads to
                .font(.footnote.weight(.semibold)).foregroundStyle(.secondary).monospacedDigit()
                .lineLimit(1).minimumScaleFactor(0.8)
                .accessibilityLabel("\(use?.name ?? ""), serie 1: \(Fmt.set(model.kg, model.reps))")
            ViewThatFits(in: .vertical) {
                rows(ramp)
                ScrollView { rows(ramp) }.scrollBounceBehavior(.basedOnSize)
            }
            .padding(.top, 3)
            Spacer(minLength: 0)
            Button { model.startSets() } label: {
                Text("Empezar series").font(.title3.weight(.bold)).lineLimit(1).minimumScaleFactor(0.8)
                    .frame(maxWidth: .infinity, minHeight: Metrics.primaryHeight)
            }
            .glassButton(tint: Theme.accentFill, covered: covered, radius: 21)
            .frame(height: Metrics.primaryHeight)
            .handGestureShortcut(.primaryAction, isEnabled: doubleTap)
            .accessibilityHint("Va a la serie 1. No registra nada.")
            .accessibilityIdentifier("startSets")
        }
    }

    private func rows(_ ramp: [PlannedSet]) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(ramp.enumerated()), id: \.offset) { i, step in
                let kg = step.weightKg ?? 0
                ViewThatFits(in: .horizontal) { // plates beside the set, else under it
                    HStack(alignment: .firstTextBaseline, spacing: 4) { set(step); Spacer(minLength: 4); plates(kg) }
                    VStack(alignment: .leading, spacing: 0) { set(step); plates(kg) }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Paso \(i + 1) de \(ramp.count), \(Fmt.kg(kg)) kilos por \(step.reps ?? 0)"
                                    + (model.plates.map { ". " + PlateMath.spoken(total: kg, start: $0.start, sides: $0.sides) } ?? ""))
                .accessibilityIdentifier("warmupStep\(i + 1)")
            }
        }
    }

    private func set(_ step: PlannedSet) -> some View {
        Text(Fmt.set(step.weightKg, step.reps)).font(.body.weight(.semibold)).monospacedDigit().lineLimit(1).fixedSize()
    }

    @ViewBuilder private func plates(_ kg: Double) -> some View {
        if let p = model.plates {
            PlateLine(total: kg, start: p.start, sides: p.sides, compact: true)
                .font(.footnote).foregroundStyle(.secondary).fixedSize()
        }
    }
}

/// G68: the plates for a total, count first ("2×25 · 10"), and what they can't make in caution ("+0,5/lado"). The
/// glyph is decoration; VoiceOver reads "Por lado: 2 de 25 y 1 de 10". Read-only: it never rounds the kg (G14).
struct PlateLine: View {
    let total: Double
    let start: Double
    let sides: Int
    var compact = false

    var body: some View {
        let l = PlateMath.line(total: total, start: start, sides: sides)
        HStack(spacing: 4) {
            if !compact { Image(systemName: "dumbbell.fill").accessibilityHidden(true) }
            if !l.text.isEmpty { Text(l.text).foregroundStyle(compact ? .secondary : .primary) }
            if let w = l.warning { Text(w).foregroundStyle(Theme.caution) }
        }
        .monospacedDigit()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(PlateMath.spoken(total: total, start: start, sides: sides))
        .accessibilityIdentifier("plateLine")
    }
}

/// "⇄ Cambiar ejercicio" (G69, option A): the coach's alternatives (minus the one in use), then "Otro (en el iPhone)".
/// A pick swaps at once and returns to the Set page: no confirm, nothing is lost, "↶ Volver a …" is the way back.
/// "Otro" waits here for the phone's pick; closing the sheet cancels it. Double Tap does nothing here.
struct SwapSheet: View {
    let done: () -> Void
    @Environment(WatchModel.self) private var model

    var body: some View {
        Group {
            if model.swapRequest != nil { waiting } else { list }
        }
        // The phone's pick arrived (or a pick here): back to the Set page.
        .onChange(of: model.currentSlot.flatMap { model.session?.currentExercise(forSlot: $0)?.exerciseTemplateId }) { done() }
        .onDisappear { model.cancelSwapRequest() }
    }

    private var list: some View {
        List {
            Section {
                ForEach(model.swapChoices, id: \.templateId) { alt in
                    Button { model.swap(to: alt.templateId, title: alt.name); done() } label: {
                        Text(alt.name).font(.headline).lineLimit(3)
                    }
                    .accessibilityIdentifier("alt.\(alt.templateId)")
                }
                Button { model.requestSwap() } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "iphone").foregroundStyle(Theme.accent)
                        VStack(alignment: .leading, spacing: 1) {
                            Text("Otro").font(.headline)
                            Text("Elige en el iPhone").font(.footnote).foregroundStyle(.secondary)
                        }
                    }
                }
                .accessibilityIdentifier("swapOther")
            } header: {
                Text(header).font(.footnote).textCase(nil)
            }
        }
        .navigationTitle("Cambiar")
    }

    /// "Press banca · quedan 3" (panel copy): the exercise in use and the working sets still to do.
    private var header: String {
        let total = model.currentSlot.map { model.plan?.setCount($0, added: model.addedSets) ?? 0 } ?? 0
        return "\(model.currentInUse?.short ?? "") · quedan \(max(total - model.confirmedInSlot.working.count, 0))"
    }

    private var waiting: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Image(systemName: "iphone").font(.title2).foregroundStyle(Theme.accent).accessibilityHidden(true)
                Text("Elige en el iPhone").font(.headline)
                Text("Abre Athlete OS en el iPhone. El cambio aparecerá aquí.").font(.footnote).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                if model.swapSilent {
                    Text("El iPhone no responde.").font(.footnote).foregroundStyle(Theme.caution)
                        .accessibilityIdentifier("swapSilent")
                }
                Button { model.cancelSwapRequest() } label: {
                    Text("Cancelar").font(.headline).frame(maxWidth: .infinity, minHeight: 40)
                }
                .glassButton(radius: 20)
                .padding(.top, 4)
                .accessibilityIdentifier("swapCancel")
            }
            .padding(.horizontal, 4)
        }
        .accessibilityIdentifier("swapWaiting")
    }
}

/// The rest half of the Set page (G8/G9, audit #2): countdown beside the clock (content, not a target) · rest
/// bar + "+30 s" · −15 Saltar +15 (8 pt apart, 38 pt, well below the top edge) · "RIR · name S2" (the gap) ·
/// RIR chips 38 pt · Siguiente.
struct RestLayer: View {
    let isFront: Bool
    /// The flip lockout is over; the controls and Cambiar wait for it, the RIR chips don't (audit #4).
    let touchOK: Bool
    let change: () -> Void
    @Environment(WatchModel.self) private var model

    var body: some View {
        let now = Date.now
        let end = model.restEnd ?? now
        let start = min(model.restStart ?? now, end)
        VStack(spacing: 0) {
            Text(timerInterval: start...end, countsDown: true)
                .font(.system(size: Metrics.countdown, weight: .semibold, design: .rounded).monospacedDigit())
                .lineLimit(1).minimumScaleFactor(0.6)
                .foregroundStyle(Theme.elapsed)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.leading, 3).padding(.trailing, 43) // the clock keeps its corner (Band: 52 pt)
                .frame(height: 42)
                .padding(.bottom, -6) // the digits' descender space; the bar sits just under them
                .accessibilityIdentifier("restTimer")
            HStack(spacing: 6) {
                RestBar(start: start, end: end, base: model.restBase)
                NudgeChip(seconds: model.nudge)
            }
            .frame(height: 15)
            .padding(.top, 4)
            HStack(spacing: 8) {
                RestStep(sign: -1) { model.step($0); model.crownSettled() }
                Button { model.skipRest() } label: {
                    Text("Saltar").font(.headline).lineLimit(1).frame(maxWidth: .infinity, minHeight: 38, maxHeight: 38)
                }
                .glassButton(radius: 19)
                .handGestureShortcut(.primaryAction, isEnabled: isFront) // Double Tap during rest = skip it
                .accessibilityIdentifier("skipRest")
                RestStep(sign: 1) { model.step($0); model.crownSettled() }
            }
            .allowsHitTesting(touchOK)
            .padding(.top, 4)
            // Audit #2: the label line is the gap (≥ 12 pt) between Saltar/±15 and the chips, and says which set
            // the chips rate — the one whose Hecho started this rest.
            rirLabel.padding(.vertical, 2)
            if let slot = model.restSlot, let i = model.restRIRIndex {
                RIRChips(selected: model.session?.sets(forSlot: slot)[safe: i]?.rir,
                         set: { model.setRIR($0, slot: slot, index: i) }, height: 38)
            }
            NextCard(change: change).padding(.top, 6).allowsHitTesting(touchOK)
        }
        .padding(.horizontal, Metrics.sidePadding)
        .padding(.top, 2)
        .padding(.bottom, Metrics.dotsClearance)
    }

    /// "RIR · Press inclinado S2": the exercise and set the chips apply to (audit #5). The name gives way first.
    private var rirLabel: some View {
        let sets = model.restSlot.flatMap { model.session?.sets(forSlot: $0) } ?? []
        let use = model.inUse(model.restSlot) // the substitute after a swap (G69)
        let name = use?.short ?? ""
        let set = sets.last.map { $0.type == .warmup ? "Calent." : "S\(sets.working.count)" } ?? ""
        return HStack(spacing: 4) {
            Text("RIR · \(name)").lineLimit(1).truncationMode(.tail)
            Text(set).fixedSize()
        }
        .font(.footnote.weight(.bold)).foregroundStyle(.secondary)
        .frame(maxWidth: .infinity, minHeight: 16, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Repeticiones en reserva de \(use?.name ?? ""), \(set == "Calent." ? "calentamiento" : "serie \(sets.working.count)")")
        .accessibilityIdentifier("rirLabel")
    }
}

/// "Siguiente": the set the Set page shows after the rest. When the exercise changes it names it, and the
/// whole card is the "Cambiar ›" button (L4: no silent jump; a ≥ 60 pt target instead of a small chip).
struct NextCard: View {
    let change: () -> Void
    @Environment(WatchModel.self) private var model

    var body: some View {
        let newExercise = model.currentSlot != model.restSlot
        let canChange = newExercise && model.pendingSlots.count > 1
        if canChange { // the whole block is the Cambiar button; no card background (G9), "Cambiar ›" says it
            Button(action: change) { content(newExercise: newExercise, canChange: true) }
                .buttonStyle(.plain)
                .accessibilityLabel("\(spoken). Cambiar")
                .accessibilityIdentifier("changeNext")
        } else { // plain content, not a control: no glass
            content(newExercise: newExercise, canChange: false)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(spoken) // the full name in every case, never the short one on screen
                .accessibilityIdentifier("nextCard")
        }
    }

    /// VoiceOver: "Siguiente: Press inclinado con barra, serie 2 de 3, 102,5 por 12" (or "Todo hecho…").
    private var spoken: String {
        guard let key = model.currentSlot, let slot = model.currentPlanSlot, let p = model.livePrefill else {
            return "Siguiente: todo hecho, termina en Resumen"
        }
        let total = slot.plannedSets.count + (model.addedSets[key] ?? 0)
        let set = "serie \(model.confirmedInSlot.working.count + 1) de \(total)"
        let kg = p.weightKg.map { "\(Fmt.kg($0)) kilos" } ?? "sin peso"
        return "Siguiente: \(model.currentInUse?.name ?? slot.name), \(set), \(kg) por \(p.reps.map(String.init) ?? "—")"
    }

    private func content(newExercise: Bool, canChange: Bool) -> some View {
        // Q26: the coach's short name (full when there is none); long ones still step down to 13 pt, then two lines.
        ViewThatFits { // both axes: a name too wide for one line must not widen the page
            block(newExercise: newExercise, canChange: canChange, name: nextName.font(.headline), setLine: true)
            block(newExercise: newExercise, canChange: canChange, name: nextName.font(.footnote.weight(.semibold)), setLine: true)
            block(newExercise: newExercise, canChange: canChange, name: nextName.font(.footnote.weight(.semibold)), setLine: false, lines: 2)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .contentShape(Rectangle())
    }

    private var nextName: Text { Text(model.currentInUse?.short ?? "") } // VoiceOver reads the full name (`spoken`)

    private func block(newExercise: Bool, canChange: Bool, name: Text, setLine: Bool, lines: Int = 1) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 4) {
                Text("Siguiente").font(.footnote.weight(.bold)).foregroundStyle(Theme.elapsed)
                Spacer(minLength: 0)
                if canChange {
                    Text("Cambiar ›").font(.footnote.weight(.bold)).foregroundStyle(Theme.accent)
                }
            }
            if newExercise, model.currentPlanSlot != nil {
                name.lineLimit(lines).fixedSize(horizontal: lines == 1, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            if let key = model.currentSlot, let slot = model.currentPlanSlot, let p = model.livePrefill {
                if setLine || !newExercise {
                    let total = slot.plannedSets.count + (model.addedSets[key] ?? 0)
                    Text("Serie \(model.confirmedInSlot.working.count + 1)/\(total) · \(Fmt.set(p.weightKg, p.reps))")
                        .font(.body).monospacedDigit().foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.85)
                }
            } else {
                Text("Todo hecho · termina en Resumen").font(.body).lineLimit(1).minimumScaleFactor(0.85)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// "Cambiar": the exercises with sets still to do, in routine order. Overview stays the free-choice route.
struct ChangeNextSheet: View {
    let done: () -> Void
    @Environment(WatchModel.self) private var model

    var body: some View {
        List(model.pendingSlots, id: \.self) { key in
            if let slot = model.plan?.slots[key] {
                Button { model.select(key); done() } label: {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(model.inUse(key)?.name ?? slot.name).font(.headline).lineLimit(2)
                        Text(slot.target.map { "\(Fmt.kg($0.kg)) kg · \(Fmt.reps($0.repsList))" } ?? "Sin objetivo")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                    .foregroundStyle(Theme.neon && key == model.currentSlot ? Theme.onAccent : .primary) // black on neon
                }
                .listItemTint(key == model.currentSlot ? Theme.accentFill : nil)
                .accessibilityIdentifier("next.\(key)")
            }
        }
        .navigationTitle("Siguiente")
    }
}

// MARK: - Overview / controls

/// Resumen (L12): sync banner + time/HR/sets → every slot in routine order (tap one to make it current) →
/// Terminar (hold + confirm) → apart and quieter, Descartar sesión.
struct OverviewPage: View {
    let onPick: () -> Void
    /// Previews only: where the list starts (`.bottom` = Terminar).
    var anchor: UnitPoint? = nil
    @Environment(WatchModel.self) private var model
    @State private var confirmEnd = false
    @State private var confirmDiscard = false

    var body: some View {
        let sets = model.session?.exercises.reduce(0) { $0 + $1.sets.count } ?? 0
        VStack(spacing: 0) {
            Band { SyncPill(state: model.syncState(model.session)) }
            ScrollViewReader { proxy in
            List {
                summary
                rows
                Section {
                    FinishButton(covered: confirmEnd || confirmDiscard) { confirmEnd = true }.id("finishRow")
                }
                Section { // its own section, well below Terminar; same glass, red text (G10)
                    Button { confirmDiscard = true } label: {
                        Text("Descartar sesión").font(.body.weight(.semibold)).foregroundStyle(Theme.missed)
                            .frame(maxWidth: .infinity, minHeight: 40)
                    }
                    .glassButton(covered: confirmEnd || confirmDiscard, radius: 20)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets())
                    .accessibilityIdentifier("discard")
                } footer: {
                    if !model.status.isEmpty { Text(model.status) }
                }
            }
            .contentMargins(.bottom, 34, for: .scrollContent) // the last row (Descartar) ends above the page dots (G5)
            .defaultScrollAnchor(anchor)
            .task(id: model.showFinish) { // G22; runs once the page is on screen (an off-screen page misses changes)
                guard model.showFinish else { return }
                try? await Task.sleep(for: .seconds(0.4)) // after the page swipe settles, or the list ignores it
                withAnimation { proxy.scrollTo("finishRow", anchor: .center) }
                model.showFinish = false
            }
            }
        }
        .sessionPage()
        .confirmationDialog("¿Terminar sesión?", isPresented: $confirmEnd, titleVisibility: .visible) {
            Button("Terminar") { Task { await model.finish() } }
            Button("Seguir") {}
        } message: {
            if sets == 0 { Text("Sin series: no se guarda en Salud.") } // N9: never a silent discard
        }
        .confirmationDialog("¿Descartar sesión?", isPresented: $confirmDiscard, titleVisibility: .visible) {
            Button("Seguir") {} // the safe choice comes first
            Button("Descartar", role: .destructive) { Task { await model.discard() } }
        } message: {
            Text(sets == 1 ? "Se pierde 1 serie. No se guarda en Salud." : "Se pierden \(sets) series. No se guarda en Salud.")
        }
    }

    private var summary: some View {
        let p = model.progress // the one count (G79)
        return VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Elapsed(start: model.session?.startedAt)
                Heart()
            }
            Text("\(p.done)/\(p.planned) series").font(.footnote.weight(.semibold)).monospacedDigit()
        }
        .listRowBackground(Color.clear)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var rows: some View {
        if let plan = model.plan, let rk = model.routineKey, plan.routines[rk] != nil {
            // G39: a superset's members sit together under "Superserie".
            ForEach(plan.supersetRuns(routineKey: rk), id: \.self) { run in
                if run.count > 1 {
                    Section {
                        ForEach(run, id: \.self) { slotRow($0, plan: plan) }
                    } header: {
                        Label("Superserie", systemImage: "link").font(.footnote.weight(.bold)).foregroundStyle(Theme.elapsed)
                            .accessibilityIdentifier("supersetGroup")
                    }
                } else {
                    slotRow(run[0], plan: plan)
                }
            }
        } else {
            Text("La rutina «\(model.session?.routineTitle ?? "")» no está en el plan recibido.")
        }
    }

    @ViewBuilder private func slotRow(_ key: String, plan: Plan) -> some View {
                if let slot = plan.slots[key] {
                    let sets = model.session?.sets(forSlot: key) ?? []
                    let total = plan.setCount(key, added: model.addedSets)
                    let blocked = slot.templateId == nil
                    let isDone = sets.working.count >= total && total > 0 // warm-ups count for nothing (N7)
                    let isCurrent = key == model.currentSlot && !isDone
                    Button { model.select(key); onPick() } label: {
                        HStack(alignment: .top, spacing: 7) {
                            Image(systemName: isDone ? "checkmark.circle.fill" : isCurrent ? "play.circle.fill" : "circle")
                                .font(.body)
                                .foregroundStyle(isDone ? Theme.done : isCurrent ? Theme.accent : .secondary)
                            VStack(alignment: .leading, spacing: 1) {
                                let use = slot.inUse(model.session?.currentExercise(forSlot: key))
                                Text(use.short).accessibilityLabel(use.name).font(.body.weight(isCurrent ? .bold : .regular)).lineLimit(2)
                                    .foregroundStyle(isDone ? .secondary : .primary)
                                if use.substituted { // the 3B graft: what it replaced, display only
                                    Text("⇄ En vez de \(slot.short)").font(.footnote).foregroundStyle(Theme.elapsed)
                                        .lineLimit(2).accessibilityLabel("En vez de \(slot.name)")
                                }
                                Text(blocked ? "Sin ID de ejercicio"
                                     : isDone ? "Completado · \(sets.working.count)/\(total)"
                                     : "\(isCurrent ? "ahora · " : "")\(sets.working.count)/\(total) · \(ladder(slot))")
                                    .font(.footnote).foregroundStyle(isDone ? Theme.done : isCurrent ? Theme.accent : .secondary)
                                    .monospacedDigit()
                                if sets.contains(where: { $0.type != .normal }) { SpecialBadges(sets: sets) }
                            }
                        }
                    }
                    .disabled(blocked)
                    .accessibilityIdentifier("slot.\(key)")
                }
    }

    private func ladder(_ slot: Plan.Slot) -> String {
        slot.target.map { "\(Fmt.kg($0.kg)) kg · \(Fmt.reps($0.repsList))" } ?? "\(slot.prescription.sets) series"
    }
}

/// Terminar: hold 1 s (the screen floods in the accent, G1), then confirm (Q21, N15).
struct FinishButton: View {
    let covered: Bool
    let action: () -> Void

    var body: some View {
        HoldButton(title: "Terminar", hint: "Mantén pulsado", verb: "Terminar", color: Theme.accentFill, label: Theme.onAccent,
                   fillLabel: Theme.onAccent, duration: 1, covered: covered, radius: 22, action: action)
            .frame(height: 48)
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets())
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Terminar sesión")
            .accessibilityHint("Mantén pulsado para terminar.")
            .accessibilityAddTraits(.isButton)
            .accessibilityAction(.default, action)
            .accessibilityIdentifier("finish")
    }
}

/// "Registrada ✓" on a logged set: hold 1 s (`Unlog.hold`) to un-log it — green glass; while held the screen
/// floods green with a black label (G1); a tap only bolds the hint, Double Tap never acts.
struct UnlogButton: View {
    var covered = false
    let action: () -> Void

    var body: some View {
        // Neón verde: white + ✓, never green (green is the accent there, G43).
        HoldButton(title: "Registrada ✓", hint: "Mantén para quitar", verb: "Quitar serie", color: Theme.done, label: .black,
                   fillLabel: .black, duration: Unlog.hold, covered: covered, action: action)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Serie registrada")
            .accessibilityHint("Mantén pulsado un segundo para desmarcarla. Podrás deshacerlo 4 segundos.")
            .accessibilityAddTraits(.isButton)
            .accessibilityAction(named: "Desmarcar serie", action)
            .accessibilityIdentifier("logged")
    }
}

// MARK: - Start countdown (L9)

/// 3 → 2 → 1 → "¡Vamos!", full screen, Apple Workout style: a ring fills once per second around big rounded
/// numerals in the accent. Tap anywhere or Double Tap = start now. Reduce Motion: the ring stays full and the
/// numbers change without animation. Nothing here ever logs.
struct CountdownView: View {
    @Environment(WatchModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let began = model.countdown?.began ?? .now
        Button { model.skipCountdown() } label: {
            TimelineView(.animation(minimumInterval: reduceMotion ? 1 : 1.0 / 30, paused: model.goAt != nil)) { ctx in
                let elapsed = ctx.date.timeIntervalSince(began)
                let n = model.goAt != nil ? 0 : Countdown.number(at: elapsed)
                let fill = n == 0 || reduceMotion ? 1 : elapsed - elapsed.rounded(.down)
                ZStack {
                    Circle().stroke(.white.opacity(0.18), lineWidth: 9)
                    Circle().trim(from: 0, to: fill)
                        .stroke(Theme.accent, style: StrokeStyle(lineWidth: 9, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                    Group {
                        if n > 0 {
                            Text("\(n)").font(.system(size: 84, weight: .bold, design: .rounded).monospacedDigit())
                        } else {
                            Text("¡Vamos!").font(.system(size: 32, weight: .heavy, design: .rounded))
                                .lineLimit(1).minimumScaleFactor(0.7)
                        }
                    }
                    .foregroundStyle(Theme.accent)
                    .contentTransition(reduceMotion ? .identity : .numericText(countsDown: true))
                    .animation(reduceMotion ? nil : .snappy(duration: 0.25), value: n)
                }
                .padding(18)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(n > 0 ? "\(n)" : "¡Vamos!")
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .handGestureShortcut(.primaryAction) // Double Tap = start now
        .accessibilityHint("Toca para empezar ya.")
        .accessibilityIdentifier("countdown")
        .ignoresSafeArea()
        .background(.black)
    }
}

// MARK: - Métricas (L10, G79, G97, G99)

/// Right of the Set page: three Crown views, one screen each (G79 direction D, G97, G99) — **Métricas** (Apple
/// Workout's glance: glyph, yellow elapsed, ♥ PPM, KCAL ACTIVAS, KG MOVIDOS, SERIES), **Zonas** (zone pills, HR, % of
/// the estimated max, media, máx) and **Pulso** (HR graph, recovery). G99: the system vertical page `TabView`, as in
/// Apple Workout — the Crown (and a vertical swipe) pages with Apple's own full-screen transition that follows the
/// turn, instead of G97's custom detent that jumped on a tiny turn. It is disabled unless Métricas is in front and
/// awake, so it can never take the Crown from the Set page's kg / ±15 (G26, G38). The index lives in the model;
/// wrist-down sets it back to 0 (one Always On layout). Paging edits nothing: the written exception to DESIGN
/// principle 2. The system Crown ticks are the only haptic.
struct MetricsPage: View {
    let isFront: Bool
    @Environment(WatchModel.self) private var model
    @Environment(\.isLuminanceReduced) private var dim

    static let views = ["Métricas", "Zonas", "Pulso"]

    var body: some View {
        @Bindable var model = model
        TabView(selection: $model.metricsView) {
            MetricsGlance().view(0).tag(0)
            ZonesView().view(1).tag(1)
            // Drawn only while Métricas is in front: the chart never re-draws behind the Set page (G25).
            Group { if isFront { PulseView() } else { Color.clear } }.view(2).tag(2)
        }
        .tabViewStyle(.verticalPage)
        .disabled(!isFront || dim)
        .sessionPage()
        .dynamicTypeSize(...DynamicTypeSize.xLarge)
        .accessibilityIdentifier("metrics")
    }
}

private extension View {
    /// One Crown view, a full screen: "Zonas, vista 2 de 3" for VoiceOver.
    func view(_ i: Int) -> some View {
        frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .ignoresSafeArea(edges: [.top, .bottom])
            .accessibilityElement(children: .contain)
            .accessibilityLabel("\(MetricsPage.views[i]), vista \(i + 1) de \(MetricsPage.views.count)")
            .accessibilityIdentifier("metricsView\(i)")
    }
}

/// Glance row (Apple Workout): a big white value, then a small two-line caps unit top-aligned to the numerals.
/// Apple density (G97, G99, G107): the row height is the pitch; the value keeps its own line box (it may overhang the
/// row's empty top/bottom, never the next row's ink). G107: 32 pt digits (ink ≈ 21,8 pt) on 29 pt rows = ink/pitch 0,75,
/// measured against Apple Workout scaled to 42 mm (29,4 pt pitch, 0,72). Units 12 pt bold (cap ≈ 7,8, Apple's 7,7) on a
/// 12 pt pitch beside 32 pt digits, 11 beside smaller ones: the unit block is never taller than the digits.
private struct MetricRow<Unit: View>: View {
    let value: String
    var size: CGFloat = 32
    var height: CGFloat = 29
    var heart = false
    @ViewBuilder let unit: Unit
    @Environment(\.isLuminanceReduced) private var dim

    var body: some View {
        let u: CGFloat = 12
        let pitch: CGFloat = size >= 32 ? 12 : 11
        HStack(alignment: .top, spacing: 4) {
            Text(value).font(.system(size: size, weight: .semibold, design: .rounded).monospacedDigit())
                .foregroundStyle(dim ? .white.opacity(0.75) : .white)
                .contentTransition(.numericText())
                .fixedSize(horizontal: false, vertical: true)
            if heart {
                Image(systemName: "heart.fill").font(.system(size: size * 0.5, weight: .bold)).foregroundStyle(Theme.missed)
                    .padding(.top, size * 0.22)
            }
            // SF Rounded's cap top sits ~0,246 em under its line top: shift the units so both cap tops meet.
            VStack(alignment: .leading, spacing: pitch - u * 1.19) { unit } // 1,19 em = the line height
                .font(.system(size: u, weight: .bold, design: .rounded)).foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 0.246 * (size - u))
        }
        .lineLimit(1).minimumScaleFactor(0.8)
        .frame(maxWidth: .infinity, minHeight: height, maxHeight: height, alignment: .topLeading)
        .accessibilityElement(children: .ignore)
    }
}

/// View 1: the glance. Rows are fixed and show "—" until there is data (MT-17). G107: 32 pt on 29 pt rows (G99 had
/// 32 on 32), Apple Workout's measured pitch.
private struct MetricsGlance: View {
    @Environment(WatchModel.self) private var model
    @Environment(\.isLuminanceReduced) private var dim

    var body: some View {
        let volume = model.session.map(Stats.volume) ?? 0
        let p = model.progress
        ZStack(alignment: .topLeading) {
            Image(systemName: "dumbbell.fill")
                .font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.accent)
                .frame(width: 26, height: 26)
                .background { if dim { Circle().stroke(Theme.accent, lineWidth: 1) } else { Circle().fill(Theme.accent.opacity(0.24)) } }
                .padding(.leading, 24).padding(.top, 12) // clear of the screen's rounded corner
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 0) {
                if let start = model.session?.startedAt { MetricsClock(start: start, dim: dim) }
                GlanceHeart()
                MetricRow(value: model.activeKcal.map { Fmt.whole($0) } ?? "—") { Text("KCAL"); Text("ACTIVAS") }
                    .accessibilityLabel(model.activeKcal.map { "\(Fmt.whole($0)) kilocalorías activas" } ?? "Kilocalorías activas: sin datos")
                MetricRow(value: Fmt.whole(volume)) { Text("KG"); Text("MOVIDOS") }
                    .accessibilityLabel("\(Fmt.whole(volume)) kilos movidos")
                    .accessibilityIdentifier("kgMoved")
                MetricRow(value: "\(p.done)/\(p.planned)") { Text("SERIES") }
                    .accessibilityLabel("\(p.done) de \(p.planned) series hechas")
                    .accessibilityIdentifier("seriesDone")
            }
            .padding(.top, 36)
            .padding(.leading, 12).padding(.trailing, 12)
        }
    }
}

/// Yellow elapsed time, whole seconds only (G99: no hundredths anywhere): the system timer, `38:16` once a second in
/// Always On.
private struct MetricsClock: View {
    let start: Date
    let dim: Bool

    var body: some View {
        Group {
            if dim {
                TimelineView(.periodic(from: start, by: 1)) { ctx in Text(Stats.elapsed(ctx.date.timeIntervalSince(start))) }
            } else {
                Text(timerInterval: start...Date.distantFuture, countsDown: false)
            }
        }
        .font(.system(size: 32, weight: .semibold, design: .rounded).monospacedDigit())
        .foregroundStyle(Theme.elapsed)
        .lineLimit(1).minimumScaleFactor(0.7)
        .fixedSize(horizontal: false, vertical: true)
        .frame(height: 29, alignment: .top) // 29 pt pitch (G107), the line box may overhang
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Tiempo de sesión")
        .accessibilityValue(Stats.elapsed(Date.now.timeIntervalSince(start)))
    }
}

/// `130 ♥ Z3/PPM`: white number, red heart, the zone label in its colour. Its own view so a reading redraws only this
/// row; re-checked every 5 s so a reading older than 15 s turns into "—" (MT-05).
private struct GlanceHeart: View {
    @Environment(WatchModel.self) private var model
    var body: some View {
        TimelineView(.periodic(from: .now, by: 5)) { ctx in
            let bpm = model.liveHeartRate(at: ctx.date)
            let zone = bpm.map { HRZones.zone($0, max: model.maxHR) }
            MetricRow(value: bpm.map { String(Int($0)) } ?? "—", heart: true) {
                if let zone { Text("Z\(zone)").foregroundStyle(Theme.zones[zone - 1]) }
                Text("PPM")
            }
            .accessibilityLabel(bpm.map { "\(Int($0)) pulsaciones por minuto, zona \(zone!) de 5, estimada" } ?? "Sin pulso")
        }
    }
}

/// View 2: Apple's heart-rate zone view on our estimated zones (Tanaka max, never Apple's).
private struct ZonesView: View {
    @Environment(WatchModel.self) private var model
    @Environment(\.isLuminanceReduced) private var dim

    var body: some View {
        TimelineView(.periodic(from: .now, by: 5)) { ctx in
            let max = model.maxHR
            let bpm = model.liveHeartRate(at: ctx.date)
            let zone = bpm.map { HRZones.zone($0, max: max) }
            let all = model.hrSamples.map(\.bpm)
            VStack(alignment: .leading, spacing: 0) {
                pills(zone).padding(.bottom, 5)
                MetricRow(value: bpm.map { String(Int($0)) } ?? "—", size: 42, height: 38, heart: true) { EmptyView() }
                    .accessibilityLabel(bpm.map { "\(Int($0)) pulsaciones por minuto" } ?? "Sin pulso")
                MetricRow(value: bpm.map { "\(HRZones.percentOfMax($0, max: max)) %" } ?? "—", size: 29, height: 26) { Text("DEL"); Text("MÁX") }
                    .accessibilityLabel(bpm.map { "\(HRZones.percentOfMax($0, max: max)) por ciento del máximo estimado" } ?? "Sin pulso")
                MetricRow(value: all.isEmpty ? "—" : "\(Int(all.reduce(0, +) / Double(all.count)))", size: 29, height: 26) { Text("PPM"); Text("MEDIA") }
                    .accessibilityLabel(all.isEmpty ? "Media: sin datos" : "Media \(Int(all.reduce(0, +) / Double(all.count))) pulsaciones")
                MetricRow(value: all.max().map { "\(Int($0))" } ?? "—", size: 29, height: 26) { Text("PPM"); Text("MÁX") }
                    .accessibilityLabel(all.max().map { "Máximo \(Int($0)) pulsaciones" } ?? "Máximo: sin datos")
                Text(model.hrSince.map { "Desde \(Fmt.time($0)) · zonas estimadas" } ?? "Zonas estimadas · máx \(Int(max))")
                    .font(.footnote).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.8)
                    .padding(.top, 6) // clear of the last row's overhanging line box (G97)
            }
            .padding(.top, 32).padding(.horizontal, 12)
        }
    }

    /// Five pills, the current one wide with "ZONA 3" in black; not targets. No reading: all five outlined.
    private func pills(_ zone: Int?) -> some View {
        HStack(spacing: 3) {
            ForEach(1...5, id: \.self) { i in
                let c = Theme.zones[i - 1], on = i == zone
                Text(on ? "ZONA \(i)" : "\(i)")
                    .font(.system(size: 12, weight: .heavy, design: .rounded))
                    .foregroundStyle(on && !dim ? .black : c)
                    .fixedSize()
                    .padding(.horizontal, on ? 8 : 0)
                    .frame(maxWidth: on ? nil : .infinity, minHeight: 22, maxHeight: 22)
                    .layoutPriority(on ? 1 : 0) // "ZONA 3" in full; the others share what is left
                    .background { if on && !dim { Capsule().fill(c) } else { Capsule().stroke(c, lineWidth: 1.5) } }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(zone.map { "Zona \($0) de 5, estimada" } ?? "Zona: sin pulso")
    }
}

/// View 3, **Pulso** (G97, G99): the title in the clock row, the HR graph and the latest recovery. Dynamic Type text
/// (the page caps it at xLarge); the graph takes the height the text leaves, so nothing ever reaches the page dots.
/// The recovery row is always there (G99: it was hidden while no rest had a number, and read as missing): "—" until
/// a rest of 70 s or more gives one.
private struct PulseView: View {
    @Environment(WatchModel.self) private var model

    var body: some View {
        if let session = model.session {
            let samples = model.hrSamples
            let drops = Stats.recoveries(rests: model.rests, session: session, samples: samples)
            VStack(alignment: .leading, spacing: 4) {
                if samples.count >= 2 { heartGraph(samples) } else { Text("Sin pulso todavía").foregroundStyle(.secondary).frame(maxHeight: .infinity, alignment: .topLeading) }
                if let since = model.hrSince { Text("Desde \(Fmt.time(since))").font(.footnote).foregroundStyle(.secondary) }
                VStack(alignment: .leading, spacing: 0) {
                    Text("Recuperación en 60 s").font(.footnote.weight(.bold)).foregroundStyle(.secondary)
                    if let last = drops.last {
                        let l = Int(last.rounded()), mean = Int((drops.reduce(0, +) / Double(drops.count)).rounded())
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text("−\(l) ppm").font(.title3.weight(.semibold))
                            Text("media −\(mean)").foregroundStyle(.secondary)
                        }
                        .monospacedDigit().lineLimit(1).minimumScaleFactor(0.8)
                        .accessibilityLabel("Recuperación en 60 segundos: última menos \(l) pulsaciones, media menos \(mean)")
                    } else {
                        Text("—").font(.title3.weight(.semibold))
                            .accessibilityLabel("Recuperación en 60 segundos: sin datos todavía")
                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("recovery")
            }
            .font(.body)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .padding(.top, 40).padding(.leading, 12).padding(.trailing, 14).padding(.bottom, 30) // ≥ 16 pt above the dots
            .overlay(alignment: .topLeading) {
                Text("Pulso").font(.headline).lineLimit(1) // G99: was a grey footnote, too small to read
                    .padding(.top, 10).padding(.leading, 14).padding(.trailing, 60) // the system clock keeps the right
                    .accessibilityAddTraits(.isHeader)
            }
        }
    }

    private func heartGraph(_ samples: [HRSample]) -> some View {
        let max = model.maxHR
        // One line per run of the same zone, sharing the boundary reading so the line stays continuous.
        var runs: [(zone: Int, points: [HRSample])] = []
        // ≤ 90 points (G25): every reading of a long session re-drew the chart on each heart-rate update.
        for s in HRZones.downsample(samples) {
            let z = HRZones.zone(s.bpm, max: max)
            if let last = runs.last, last.zone == z { runs[runs.count - 1].points.append(s) }
            else { runs.append((z, (runs.last?.points.last.map { [$0] } ?? []) + [s])) }
        }
        let avg = samples.map(\.bpm).reduce(0, +) / Double(samples.count)
        let top = samples.map(\.bpm).max() ?? 0
        return Chart {
            ForEach(runs.indices, id: \.self) { i in
                ForEach(runs[i].points, id: \.t) { p in
                    LineMark(x: .value("Hora", p.t), y: .value("ppm", p.bpm), series: .value("Tramo", i))
                        .foregroundStyle(Theme.zones[runs[i].zone - 1])
                        .lineStyle(StrokeStyle(lineWidth: 2))
                }
            }
            RuleMark(y: .value("Media", avg))
                .foregroundStyle(.white.opacity(0.6))
                .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
        }
        .chartXAxis(.hidden)
        .chartYAxis { AxisMarks(position: .trailing, values: .automatic(desiredCount: 3)) {
            AxisValueLabel().font(.caption2).foregroundStyle(.secondary)
        } }
        .chartYScale(domain: (samples.map(\.bpm).min() ?? 60) - 5 ... top + 5) // tight: no empty band down to 0
        .frame(minHeight: 40, maxHeight: .infinity) // whatever the recovery row leaves
        .accessibilityLabel("Gráfica de pulso: media \(Int(avg)), máximo \(Int(top))")
        .accessibilityIdentifier("hrGraph")
    }
}

// MARK: - After Terminar (G41, G42)

/// The finished session: its summary, then "¿Cómo ha ido?". Nothing here can change a set (edits stay on Resumen
/// before Terminar, Q20). Stays until Listo / Saltar; nothing moves on its own.
struct FinishedView: View {
    @Environment(WatchModel.self) private var model
    @State private var asking = false

    var body: some View {
        if let f = model.finished {
            if asking { NotePrompt(note: f.session.note) } else { summary(f.session, f.summary) }
        }
    }

    /// Apple Workout's summary list: time, then value + small caps unit rows (Métricas style), records, Continuar.
    private func summary(_ s: Session, _ sum: Stats.Summary) -> some View {
        List {
            VStack(alignment: .leading, spacing: 0) {
                SyncPill(state: model.syncState(s)).padding(.bottom, 2)
                // G99/G107: Métricas' rows (32 pt values on 29 pt rows, two-line caps units), Apple Workout's summary density.
                Text(Fmt.duration(sum.duration))
                    .font(.system(size: 32, weight: .semibold, design: .rounded).monospacedDigit())
                    .foregroundStyle(Theme.elapsed).lineLimit(1).minimumScaleFactor(0.7)
                    .frame(height: 30, alignment: .leading)
                    .accessibilityLabel("Duración \(Fmt.duration(sum.duration))")
                MetricRow(value: "\(sum.setsDone)/\(sum.setsPlanned)") { Text("SERIES") }
                    .accessibilityLabel("\(sum.setsDone) de \(sum.setsPlanned) series")
                if let avg = sum.avgHR, let top = sum.maxHR {
                    MetricRow(value: "\(Int(avg))") { Text("PPM"); Text("MEDIA") }.accessibilityLabel("Pulso medio \(Int(avg))")
                    MetricRow(value: "\(Int(top))") { Text("PPM"); Text("MÁX") }.accessibilityLabel("Pulso máximo \(Int(top))")
                }
                if let kcal = sum.kcal {
                    MetricRow(value: Fmt.whole(kcal)) { Text("KCAL"); Text("ACTIVAS") }.accessibilityLabel("\(Fmt.whole(kcal)) kilocalorías activas")
                }
                MetricRow(value: Fmt.whole(sum.kg)) { Text("KG"); Text("MOVIDOS") }.accessibilityLabel("\(Fmt.whole(sum.kg)) kilos movidos")
            }
            .listRowBackground(Color.clear)
            .accessibilityIdentifier("summary")
            if let records = sum.records { // nil: no snapshot best to beat → no claim, row hidden
                VStack(alignment: .leading, spacing: 1) {
                    Text("Récords hoy").font(.footnote.weight(.bold)).foregroundStyle(.secondary)
                    if records.isEmpty { Text("Ninguno").foregroundStyle(.secondary) }
                    ForEach(records, id: \.slot) { r in
                        VStack(alignment: .leading, spacing: 0) {
                            Text(model.plan?.slots[r.slot]?.short ?? s.exercises.first { $0.slot == r.slot }?.title ?? r.slot)
                                .accessibilityLabel(model.plan?.slots[r.slot]?.name ?? s.exercises.first { $0.slot == r.slot }?.title ?? r.slot).lineLimit(2)
                            Text("\(Fmt.set(r.set.weightKg, r.set.reps)) · e1RM \(Fmt.kg((r.e1rm * 10).rounded() / 10))")
                                .foregroundStyle(Theme.elapsed).monospacedDigit()
                        }
                    }
                }
                .listRowBackground(Color.clear)
                .accessibilityElement(children: .combine)
            }
            Section {
                Button { asking = true } label: {
                    Text("Continuar").font(.headline).frame(maxWidth: .infinity, minHeight: 44)
                }
                .glassButton(tint: Theme.accentFill, radius: 22)
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets())
                .accessibilityIdentifier("summaryContinue")
            }
        }
        .contentMargins(.bottom, 16, for: .scrollContent)
        .navigationTitle(s.routineTitle)
    }
}

/// "¿Cómo ha ido?" (G42): the system text input — dictation first on watchOS, Scribble/keyboard as fallback — or
/// Saltar. The note is saved (new rev, sent) as soon as the system input's Done is tapped, and shown here as saved.
struct NotePrompt: View {
    let note: String?
    @Environment(WatchModel.self) private var model

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("¿Cómo ha ido?").font(.title3.weight(.bold))
            Group {
                if let note {
                    Label { Text(note).lineLimit(3) } icon: { Image(systemName: "checkmark").foregroundStyle(Theme.done) }
                        .accessibilityIdentifier("noteSaved")
                } else {
                    Text("Nota para el coach.").foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
            }
            .font(.body)
            .frame(maxWidth: .infinity, alignment: .leading)
            Spacer(minLength: 0)
            TextFieldLink(prompt: Text("Dicta o escribe")) {
                Label(note == nil ? "Dictar nota" : "Cambiar nota", systemImage: "mic.fill").font(.headline)
                    .frame(maxWidth: .infinity, minHeight: 44)
            } onSubmit: { model.saveNote($0) }
            .glassButton(tint: note == nil ? Theme.accentFill : nil, radius: 22)
            .accessibilityIdentifier("dictateNote")
            Button { model.closeSummary() } label: {
                Text(note == nil ? "Saltar" : "Listo").font(.headline).frame(maxWidth: .infinity, minHeight: 40)
            }
            .glassButton(tint: note == nil ? nil : Theme.accentFill, radius: 20)
            .accessibilityIdentifier("skipNote")
        }
        .padding(.horizontal, Metrics.sidePadding)
        .padding(.top, 30) // below the clock
        .padding(.bottom, 8)
        .ignoresSafeArea(edges: [.top, .bottom])
        .dynamicTypeSize(...DynamicTypeSize.xLarge)
    }
}
