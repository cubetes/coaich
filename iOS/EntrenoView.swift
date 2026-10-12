import SwiftUI
import AthleteCore

/// Entreno (G82, phase 0): the app's only screen. Segments Rutina · Sesiones under the system large title; at most one
/// freshness line (the web's rules); the settings button top-right with a red dot for sync problems.
struct EntrenoView: View {
    @Binding var showAjustes: Bool
    @Environment(PhoneModel.self) private var model
    @Environment(LiveSession.self) private var live
    @State private var segment = Segment.rutina
    /// "Otra rutina ›": the routine the athlete picked instead of the suggestion (until the app restarts).
    @State private var picked: String?
    /// A day tapped on the strip; nil = today.
    @State private var day: String?

    enum Segment: CaseIterable {
        case rutina, sesiones
        var label: LocalizedStringResource { self == .rutina ? "Rutina" : "Sesiones" }
    }

    var body: some View {
        let problems = model.outbox.problems(now: .now)
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                SegmentBar(selection: $segment)
                    .padding(.top, 8)
                if let line = freshness {
                    Label(line, systemImage: "clock")
                        .font(Magma.font(13, .semibold, relativeTo: .footnote))
                        .foregroundStyle(Magma.cautionFg)
                        .padding(.top, 12)
                }
                switch segment {
                case .rutina: RutinaPane(picked: $picked, day: $day)
                case .sesiones: SesionesPane()
                }
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 32)
        }
        .background(Magma.bg)
        .navigationTitle("Entreno")
        .navigationSubtitle(segment == .rutina ? eyebrow : "En este iPhone")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Ajustes", systemImage: "gearshape") { showAjustes = true }
                    .badge(problems) // a count, not colour alone (EN-08); none at 0
                    .accessibilityValue(problems > 0 ? "\(problems) \(problems == 1 ? "problema" : "problemas") de sincronización" : "")
            }
        }
        .refreshable { await model.refresh() }
        // G101 b: "… borrada · Deshacer" pinned at the bottom, so it shows wherever the list is scrolled and right after
        // SessionView pops back here (it sat at the top of Sesiones, off screen when the list was scrolled down).
        .safeAreaInset(edge: .bottom) {
            if let id = model.justDeleted, let s = model.outbox.items[id]?.deleted {
                UndoBanner(session: s).padding(.horizontal, 20).padding(.bottom, 8)
                    .transition(.opacity)
            }
        }
        .animation(.smooth(duration: 0.2), value: model.justDeleted)
    }

    /// The header line: the shown day and its routine ("Sáb 10 oct · Pull B").
    private var eyebrow: String {
        let today = Plan.day()
        let date = day ?? today
        let w = model.entreno?.payload.workout
        let key = Lift.shownRoutine(day: day, week: w?.week, liveKey: live.state?.routineKey, picked: picked,
                                    suggested: model.suggestion?.key)
        let title = key.flatMap { model.plan?.routines[$0]?.title ?? w?.routines?[$0]?.title }
        return [date == today ? "Hoy" : Lift.dayLabel(date), title ?? (day == nil ? nil : "Descanso")].compactMap { $0 }.joined(separator: " · ")
    }

    private var freshness: String? {
        guard model.plan != nil || model.lastRefresh != .ok else { return nil }
        let e = model.entreno
        return Lift.freshness(asOf: e?.asOfDate, meta: e?.payload.workout?.meta, refresh: model.lastRefresh, now: .now)
    }
}

/// Rutina · Sesiones (G98 b, i20). The system segmented control keeps a fixed-size label at every text size, so this is
/// two buttons with Dynamic Type text in the G73 chip style (tint fill + its G75 label when selected), side by side,
/// one under the other when they no longer fit. VoiceOver still gets the system segmented picker.
private struct SegmentBar: View {
    @Binding var selection: EntrenoView.Segment
    @AppStorage("theme") private var theme = AppTheme.magenta

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 2) { buttons }
            VStack(spacing: 2) { buttons }
        }
        .padding(3)
        .background(.fill.tertiary, in: .rect(cornerRadius: 24))
        .accessibilityRepresentation {
            Picker("Vista", selection: $selection) {
                ForEach(EntrenoView.Segment.allCases, id: \.self) { Text($0.label) }
            }
            .pickerStyle(.segmented)
        }
    }

    private var buttons: some View {
        ForEach(EntrenoView.Segment.allCases, id: \.self) { s in
            let on = selection == s
            Button { selection = s } label: {
                Text(s.label).font(Magma.font(15, .bold, relativeTo: .subheadline)) // bold ≥ 15 pt on the accent fill
                    .fixedSize()
                    .foregroundStyle(on ? AnyShapeStyle(theme.onTint) : AnyShapeStyle(Magma.text))
                    .padding(.horizontal, 12)
                    .frame(maxWidth: .infinity, minHeight: 38)
                    .background(on ? AnyShapeStyle(.tint) : AnyShapeStyle(.clear), in: .rect(cornerRadius: 21))
                    .contentShape(.rect)
            }
            .buttonStyle(.plain)
        }
    }
}

extension PhoneModel {
    /// The routine to suggest: the Watch's rule (G40), from this phone's last finished session.
    var suggestion: Plan.RoutineSuggestion? {
        let last = lastFinished
        return plan?.suggestedRoutine(lastTitle: last?.routineTitle, lastDay: last.map { Plan.day($0.startedAt) })
    }
}

// MARK: - Rutina

private struct RutinaPane: View {
    @Binding var picked: String?
    @Binding var day: String?
    @Environment(PhoneModel.self) private var model
    @Environment(LiveSession.self) private var live
    @AppStorage("theme") private var theme = AppTheme.magenta

    var body: some View {
        let today = Plan.day()
        let e = model.entreno?.payload.workout
        let order = model.plan?.rotation ?? (e?.routines?.keys.sorted() ?? [])
        if let e, e.week?.isEmpty == false {
            DayStrip(cells: Lift.weekCells(e, order: order, today: today), selected: day ?? today) { d in
                day = d == today ? nil : d
            }
            .padding(.top, 14)
        }
        Hero(picked: $picked, order: order)
            .padding(.top, 16)
        if let e {
            let shown = Lift.shownRoutine(day: day, week: e.week, liveKey: live.state?.routineKey, picked: picked,
                                          suggested: model.suggestion?.key)
            if let key = shown, let routine = e.routines?[key] {
                let liveRows = live.state.flatMap { Lift.liveRows($0, routineKey: key) }
                if let notes = routine.notesEs, !notes.isEmpty {
                    Text(notes).font(Magma.font(14, relativeTo: .subheadline)).foregroundStyle(Magma.dim).padding(.top, 14)
                }
                HStack(alignment: .firstTextBaseline) {
                    SectionLabel(text: day.map { "\(Lift.dayLabel($0)) · \(routine.title)" } ?? "Ejercicios")
                    Text(liveRows == nil ? "objetivo · semana pasada" : "hechas / plan")
                        .font(Magma.font(12, .semibold, relativeTo: .caption)).foregroundStyle(Magma.faint).fixedSize()
                }
                VStack(spacing: 0) {
                    ForEach(Array(routine.slots.enumerated()), id: \.element) { i, slotKey in
                        if let slot = e.slots?[slotKey] {
                            NavigationLink {
                                GuideView(routineKey: key, slots: routine.slots.filter { e.slots?[$0] != nil }, current: slotKey)
                            } label: {
                                SlotRow(slot: slot, targets: e.meta?.targetsStatus, live: liveRows?[slotKey],
                                        partner: partner(of: slotKey, in: routine, e))
                            }
                            .buttonStyle(.plain)
                            if i < routine.slots.count - 1 { Divider().overlay(Magma.divider).padding(.leading, 48) }
                        }
                    }
                }
                .card()
            } else if day != nil {
                Text("Descanso. Sin sesión planificada este día.")
                    .font(Magma.font(15, relativeTo: .body)).foregroundStyle(Magma.dim)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(16).card().padding(.top, 14)
            }
        } else if model.plan != nil {
            Text("El detalle del entreno (objetivos, claves, guía) no se pudo leer. El reloj tiene su plan.")
                .font(Magma.font(14, relativeTo: .subheadline)).foregroundStyle(Magma.dim).padding(.top, 14)
        }
        Text("Athlete OS \(Bundle.main.versionLabel)")
            .font(Magma.font(12, relativeTo: .caption)).foregroundStyle(Magma.faint)
            .frame(maxWidth: .infinity).padding(.top, 24)
    }

    /// "🔗 Curl barra": the superset partner in this routine, if any.
    private func partner(of key: String, in routine: Entreno.Routine, _ e: Entreno) -> String? {
        guard let id = e.slots?[key]?.superset else { return nil }
        return routine.slots.first { $0 != key && e.slots?[$0]?.superset == id }.flatMap { e.slots?[$0]?.name }
    }
}

/// The published week (state as of the last pull; never changed from this phone, EN-15). Tap a day to see its routine.
private struct DayStrip: View {
    let cells: [Lift.DayCell]
    let selected: String
    let onSelect: (String) -> Void
    @AppStorage("theme") private var theme = AppTheme.magenta
    @Environment(\.dynamicTypeSize) private var size

    var body: some View {
        let row = HStack(spacing: 6) { ForEach(cells, id: \.date) { cell($0) } }
        if size.isAccessibilitySize {
            ScrollView(.horizontal) { row }.scrollIndicators(.hidden)
        } else {
            row
        }
    }

    private func cell(_ c: Lift.DayCell) -> some View {
        let sel = c.date == selected
        return Button { onSelect(c.date) } label: {
            VStack(spacing: 4) {
                Text(c.initial).font(Magma.font(11, .bold, relativeTo: .caption2)).foregroundStyle(Magma.dim)
                Text("\(c.dayNum)").font(Magma.font(17, .heavy, relativeTo: .headline)).foregroundStyle(Magma.text)
                Text(c.label).font(Magma.font(11, .bold, relativeTo: .caption2)).foregroundStyle(Magma.dim).lineLimit(1)
                dot(c.state)
            }
            .frame(maxWidth: .infinity, minHeight: 44)
            .frame(minWidth: size.isAccessibilitySize ? 72 : nil)
            .padding(.vertical, 7)
            // Today: ink on the pale accent with an accent ring (white on the accent fill fails at this size).
            .background(c.isToday ? AnyShapeStyle(theme.soft) : sel ? AnyShapeStyle(Magma.scrim) : AnyShapeStyle(.clear), in: .rect(cornerRadius: 12))
            .overlay { if c.isToday { RoundedRectangle(cornerRadius: 12).stroke(theme.fill, lineWidth: 1.5) } }
            .overlay { if sel && !c.isToday { RoundedRectangle(cornerRadius: 12).stroke(Magma.faint, lineWidth: 1) } }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(Lift.dayLabel(c.date)) · \(c.title ?? "Descanso") · \(Lift.dayState(c.state))\(c.isToday ? " · hoy" : "")")
        .accessibilityAddTraits(sel ? .isSelected : [])
    }

    @ViewBuilder private func dot(_ state: String) -> some View {
        switch state {
        case "done": Circle().fill(Magma.hit).frame(width: 6, height: 6)
        case "planned": Circle().stroke(Magma.faint, lineWidth: 1.5).frame(width: 6, height: 6)
        case "skipped": Capsule().fill(Magma.faint).frame(width: 7, height: 2).padding(.vertical, 2)
        default: Color.clear.frame(width: 6, height: 6)
        }
    }
}

// MARK: - Hero

/// The one hero (MAGMA: Entreno's routine card): a dark card over a static accent + violet aura, never Liquid Glass.
/// States: session running (from the Watch's mirrored state) · today's routine · next in rotation · rest day ·
/// another routine picked · no plan. "Empezar en el reloj" only when no session runs and the re-link check is done.
private struct Hero: View {
    @Binding var picked: String?
    let order: [String]
    @Environment(PhoneModel.self) private var model
    @Environment(LiveSession.self) private var live
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceTransparency) private var solid
    @AppStorage("theme") private var theme = AppTheme.magenta

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let s = live.state { running(s) } else if let plan = model.plan { idle(plan) } else { empty }
        }
        .foregroundStyle(Magma.heroText)
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background {
            // Light mode: a darker fill so the small text passes 4.5:1 over the aura (panel must-fix 5).
            RoundedRectangle(cornerRadius: 22)
                .fill(solid ? Color(rgb: 0x1B1D23) : Color(rgb: 0x14161C).opacity(scheme == .dark ? 0.55 : 0.8))
                .overlay(RoundedRectangle(cornerRadius: 22).stroke(.white.opacity(0.16)))
        }
        .background {
            if !solid {
                ZStack {
                    Ellipse().fill(theme.fill).frame(width: 230, height: 170).offset(x: -70, y: -40)
                    Ellipse().fill(Magma.aura2).frame(width: 230, height: 160).offset(x: 80, y: 50)
                }
                .blur(radius: 34)
                .opacity(0.85)
                .accessibilityHidden(true)
            }
        }
        .animation(.smooth(duration: 0.2), value: live.state == nil)
        .onChange(of: live.status) { _, new in
            if !new.isEmpty { AccessibilityNotification.Announcement(new).post() }
        }
        .sensoryFeedback(trigger: live.status) { _, _ in
            live.status.isEmpty ? nil : live.statusOK ? .success : .error // only for his own tap (G47)
        }
    }

    private func eyebrow(_ text: String) -> some View { eyebrow(text, trailing: EmptyView()) }

    private func eyebrow(_ text: String, trailing: some View) -> some View {
        HStack {
            Text(text.upper)
            Spacer()
            trailing
        }
        .font(Magma.font(12, .bold, relativeTo: .caption))
        .kerning(0.8)
    }

    private func big(_ text: String) -> some View {
        Text(text.upper).font(Magma.font(34, .black, relativeTo: .largeTitle)).lineLimit(2).minimumScaleFactor(0.7)
    }

    // A running session (mirrored from the Watch). Stale like the lock-screen panel (EN-05).
    private func running(_ s: LiveState) -> some View {
        TimelineView(.periodic(from: .now, by: 15)) { ctx in runningBody(s, now: ctx.date) }
    }

    private func runningBody(_ s: LiveState, now: Date) -> some View {
            let stale = s.isResting(at: now) ? now > s.restEnd!.addingTimeInterval(30) : now.timeIntervalSince(live.received) > 20 * 60
            let segs = s.segments ?? []
            let done = segs.reduce(0) { $0 + $1.done }, planned = segs.reduce(0) { $0 + $1.planned }
            return VStack(alignment: .leading, spacing: 6) {
                eyebrow("Sesión en curso · \(s.routineTitle)", trailing: Text(s.startedAt, style: .timer).monospacedDigit())
                big(s.exercise ?? (planned > 0 && done == planned ? "Todo hecho" : s.routineTitle))
                if stale {
                    Text("Sin datos del reloj desde \(live.received.formatted(date: .omitted, time: .shortened))")
                        .font(Magma.font(15, .semibold, relativeTo: .subheadline))
                } else {
                    if let set = s.setLabel {
                        Text([set, s.targetKg.map { "\(Lift.num($0)) kg" }, s.targetReps.map { "× \($0)" }].compactMap { $0 }.joined(separator: " "))
                            .font(Magma.font(15, .semibold, relativeTo: .subheadline))
                    }
                    HStack(spacing: 18) {
                        if s.isResting(at: now), let end = s.restEnd {
                            fact(Text(timerInterval: now...end, countsDown: true).foregroundStyle(Color(rgb: 0xFFD60A)), "descanso")
                        }
                        if planned > 0 {
                            fact(Text("\(done)/\(planned)").contentTransition(.numericText()), "series")
                        }
                    }
                    .padding(.top, 6)
                }
            }
            .accessibilityElement(children: .combine)
    }

    private func fact(_ value: some View, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            value.font(Magma.font(22, .heavy, relativeTo: .title2)).monospacedDigit()
            Text(label.upper).font(Magma.font(11, .semibold, relativeTo: .caption2)).opacity(0.85)
        }
    }

    // No session: the suggestion (or the routine picked), with the start button.
    @ViewBuilder private func idle(_ plan: Plan) -> some View {
        let today = Plan.day()
        let week = model.entreno?.payload.workout?.week
        let restDay = week?.first { $0.date == today }.map { $0.routineKey == nil } ?? false
        let suggestion = model.suggestion
        if let key = picked ?? suggestion?.key, let routine = plan.routines[key] {
            let label = picked != nil ? "Otra rutina" : suggestion?.today == true ? "Hoy en el plan" : restDay ? "Descanso" : "Siguiente en la rotación"
            let sets = plan.progress(routineKey: key, session: nil, added: [:]).planned // the Watch's count (G79 one rule)
            eyebrow(label)
            big(restDay && picked == nil ? "Descanso" : routine.title)
            Text(restDay && picked == nil ? "Siguiente: \(routine.title) · \(routine.slots.count) ejercicios · \(sets) series"
                                          : "\(routine.slots.count) ejercicios · \(sets) series")
                .font(Magma.font(14, .semibold, relativeTo: .subheadline))
            startButton(key, title: restDay && picked == nil ? "Empezar \(routine.title) en el reloj" : "Empezar en el reloj")
            HStack {
                if !live.status.isEmpty {
                    Text(live.status)
                        .font(Magma.font(13, .bold, relativeTo: .footnote))
                        .foregroundStyle(live.statusOK ? Color(rgb: 0x57E099) : Color(rgb: 0xFF858A))
                }
                Spacer()
                Menu {
                    ForEach(order, id: \.self) { k in
                        Button(plan.routines[k]?.title ?? k) { picked = k == suggestion?.key ? nil : k }
                    }
                } label: {
                    Text("Otra rutina ›").font(Magma.font(14, .bold, relativeTo: .subheadline)).frame(minHeight: 44)
                }
                .foregroundStyle(Magma.heroText)
            }
        } else {
            eyebrow("Sin rutina")
            big("Entreno")
            Text("El plan no trae rutinas.").font(Magma.font(14, relativeTo: .subheadline))
        }
    }

    /// G100 b: when WatchConnectivity says the Watch app can't be reached, the button is muted ("Probar en el reloj"),
    /// the reason and the fix sit under it, and a tap still tries (iOS can be wrong about it, G44).
    @ViewBuilder private func startButton(_ key: String, title: String) -> some View {
        let problem = model.watchLink.problem
        let label = live.linking ? String(localized: "Comprobando el reloj…") : live.starting ? String(localized: "Esperando al reloj…")
            : problem != nil ? String(localized: "Probar en el reloj") : title
        let button = Button { Task { await live.startOnWatch(key) } } label: {
            Label(label, systemImage: problem != nil ? "applewatch.slash" : "applewatch")
                .font(Magma.font(17, .heavy, relativeTo: .headline))
                .frame(maxWidth: .infinity, minHeight: 52)
        }
        .buttonBorderShape(.capsule)
        .accessibilityIdentifier("startOnWatch")
        .disabled(live.linking || live.starting)
        .padding(.top, 8)
        if let problem {
            button.buttonStyle(.bordered).tint(Magma.heroText)
            Text(problem).font(Magma.font(13, .semibold, relativeTo: .footnote)).fixedSize(horizontal: false, vertical: true)
        } else {
            button.buttonStyle(.borderedProminent).tint(theme.fill).foregroundStyle(theme.onTint)
        }
    }

    @ViewBuilder private var empty: some View {
        eyebrow(model.unsupported ? "Actualiza la app" : "Sin plan")
        big("Entreno")
        Text(model.unsupported ? "El snapshot usa un formato más nuevo que esta versión."
             : "Aún no hay plan en este iPhone. Desliza hacia abajo para descargarlo.")
            .font(Magma.font(15, relativeTo: .body))
        Text("Las series se registran en el reloj.").font(Magma.font(13, relativeTo: .footnote)).opacity(0.9)
    }
}

// MARK: - Slot row

/// One exercise: ★/dumbbell, name and the coach's cue (one line; the full text is in the guide) on the left; the
/// objective with last week's mark and "Últ." under it on the right (stacked at accessibility sizes); change word and
/// tags only when there is one. While a session runs and the Watch sent its slot keys: done / planned instead.
private struct SlotRow: View {
    let slot: Entreno.Slot
    let targets: String?
    let live: Lift.LiveRow?
    let partner: String?
    @AppStorage("theme") private var theme = AppTheme.magenta
    @Environment(\.dynamicTypeSize) private var size

    var body: some View {
        let status = Lift.status(slot.target, targets: targets)
        let change = Lift.changeWord(slot.target, status: status)
        let stalled = slot.flags?.contains("stalled") == true
        let layout = size.isAccessibilitySize ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
                                              : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 10))
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: slot.priority == true ? "star.fill" : "dumbbell.fill")
                .font(.system(size: 15))
                .foregroundStyle(slot.priority == true ? AnyShapeStyle(theme.tint) : AnyShapeStyle(Magma.faint))
                .frame(width: 24)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 3) {
                layout {
                    Text(slot.name).font(Magma.font(16, .bold, relativeTo: .body)).foregroundStyle(Magma.text)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    right
                }
                if let cue = slot.cueEs, live == nil {
                    Text(cue).font(Magma.font(13.5, relativeTo: .footnote)).foregroundStyle(Magma.dim).lineLimit(1)
                }
                if live == nil, change != nil || status == .pending || stalled || slot.assisted == true || partner != nil {
                    HStack(spacing: 6) {
                        if let change {
                            Text(change).font(Magma.font(12.5, .heavy, relativeTo: .caption))
                                .foregroundStyle(slot.target?.decision == "increase" ? AnyShapeStyle(theme.tint) : AnyShapeStyle(Magma.dim))
                        }
                        if status == .pending { pill(Lift.label(.pending)) }
                        if stalled { pill("Estancado", caution: true) }
                        if slot.assisted == true { pill("Asistido") }
                        if let partner { pill("🔗 \(partner)") }
                    }
                    .padding(.top, 3)
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .contentShape(.rect)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spoken(status: status, change: change, stalled: stalled))
        .accessibilityAddTraits(.isButton)
    }

    @ViewBuilder private var right: some View {
        VStack(alignment: size.isAccessibilitySize ? .leading : .trailing, spacing: 3) {
            if let live {
                Text(live.text).font(Magma.font(14, .heavy, relativeTo: .subheadline))
                    .foregroundStyle(live.isCurrent ? AnyShapeStyle(theme.tint) : AnyShapeStyle(Magma.hitFg))
                    .contentTransition(.numericText())
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(Lift.objective(slot.target, compact: true) ?? "Sin objetivo")
                        .font(Magma.font(15, .heavy, relativeTo: .subheadline))
                        .foregroundStyle(slot.target == nil ? Magma.faint : Magma.text)
                    mark
                }
                if let last = Lift.last(slot.history, grade: slot.lastWeek?.grade) {
                    Text(last).font(Magma.font(12.5, .semibold, relativeTo: .caption)).foregroundStyle(Magma.faint)
                }
            }
        }
        .fixedSize(horizontal: !size.isAccessibilitySize, vertical: false)
    }

    private var mark: some View {
        let g = Lift.Grade(slot.lastWeek?.grade)
        return Text(g.glyph)
            .font(g == .partial ? Magma.font(12, .semibold, relativeTo: .caption) : Magma.font(14, .heavy, relativeTo: .subheadline))
            .foregroundStyle(g == .hit ? Magma.text : g == .miss ? Magma.cautionFg : g == .partial ? Magma.dim : Magma.faint)
    }

    private func pill(_ text: String, caution: Bool = false) -> some View {
        Text(text).font(Magma.font(11.5, .bold, relativeTo: .caption2))
            .foregroundStyle(caution ? Magma.cautionFg : Magma.dim)
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(caution ? Magma.cautionBg : Magma.scrim, in: .rect(cornerRadius: 6))
    }

    /// "Jalón al pecho. Objetivo 111,5 kilos, 8 repeticiones. Semana pasada: Cumplido. Últ. 111,5 por 8, 26 sep."
    private func spoken(status: Lift.Status?, change: String?, stalled: Bool) -> String {
        var parts = [slot.name]
        if let live { parts.append("\(live.done) de \(live.planned) series\(live.isCurrent ? ", ahora" : "")") }
        else {
            parts.append(Lift.objective(slot.target, compact: true).map {
                "Objetivo " + $0.replacingOccurrences(of: " kg × ", with: " kilos, ").replacingOccurrences(of: "·", with: ", ") + " repeticiones"
            } ?? "Sin objetivo")
            parts.append("Semana pasada: \(Lift.Grade(slot.lastWeek?.grade).label)")
            if let last = Lift.last(slot.history, grade: slot.lastWeek?.grade) {
                parts.append(last.replacingOccurrences(of: "Últ.", with: "Última vez").replacingOccurrences(of: " × ", with: " por "))
            }
            if let change { parts.append(change) }
            if status == .pending { parts.append(Lift.label(.pending)) }
            if stalled { parts.append("Estancado") }
            if slot.assisted == true { parts.append("Asistido") }
            if let partner { parts.append("Superserie con \(partner)") }
        }
        return parts.joined(separator: ". ")
    }
}

// MARK: - Sesiones (this phone's outbox)

/// The Watch's sessions this phone holds, by plan week, newest first; the editable one(s) on top, not repeated below
/// (EN-27). Discarded sessions are gone from the outbox, so never listed. Published (Hevy-era) sessions wait for
/// `session_id` in the snapshot (EN-25).
private struct SesionesPane: View {
    @Environment(PhoneModel.self) private var model
    @State private var toDelete: Session?
    /// The session a row tap opens (a button, not a NavigationLink, so a swipe can cancel the tap, G107 1).
    @State private var open: String?

    var body: some View {
        let now = Date.now
        let all = model.outbox.items.values.filter { $0.deleted == nil }.map(\.session) // G91: deleted ones only below
        let editable = all.filter { model.canEdit($0.id, now: now) }.sorted { $0.startedAt > $1.startedAt }
        let weeks = Lift.sessionWeeks(all.filter { !model.canEdit($0.id, now: now) },
                                      phaseStart: model.entreno?.payload.plan?.phaseStart, now: now)
        let gone = model.outbox.deleted
        VStack(alignment: .leading, spacing: 0) {
            if !editable.isEmpty {
                SectionLabel(text: String(localized: "Editable"))
                rows(editable, now: now)
            }
            ForEach(weeks, id: \.monday) { w in
                SectionLabel(text: w.title)
                rows(w.sessions, now: now)
            }
            if editable.isEmpty && weeks.isEmpty {
                Text("Aún no hay sesiones del reloj en este iPhone.")
                    .font(Magma.font(15, relativeTo: .body)).foregroundStyle(Magma.dim).padding(.top, 20)
            }
            if !gone.isEmpty { deletedList(gone) }
            Text("Sesiones de este iPhone, del reloj (últimas 8 semanas). El historial completo sigue en la web.")
                .font(Magma.font(12.5, relativeTo: .caption)).foregroundStyle(Magma.faint).padding(.top, 14)
        }
        .navigationDestination(item: $open) { SessionView(id: $0) }
        .deleteSessionDialog($toDelete) { model.deleteSession($0.id) } // one sheet for every row's swipe and menu
    }

    /// "Borradas (n) · Recuperar" (G91), collapsed: each deleted session with its way back.
    private func deletedList(_ gone: [Session]) -> some View {
        DisclosureGroup {
            VStack(spacing: 0) {
                ForEach(gone) { s in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(s.routineTitle).font(Magma.font(15, .semibold, relativeTo: .body)).foregroundStyle(Magma.text)
                            Text(s.startedAt, format: .dateTime.weekday(.abbreviated).day().month(.abbreviated))
                                .font(Magma.font(13, relativeTo: .footnote)).foregroundStyle(Magma.dim)
                        }
                        Spacer()
                        Button("Recuperar") { model.restoreSession(s.id) }
                            .font(Magma.font(15, .bold, relativeTo: .body))
                            .frame(minHeight: 44)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 6)
                }
            }
            .card()
            .padding(.top, 6)
        } label: {
            Text("Borradas (\(gone.count)) · Recuperar").font(Magma.font(13.5, .semibold, relativeTo: .footnote)).foregroundStyle(Magma.dim)
        }
        .padding(.top, 20)
    }

    private func rows(_ list: [Session], now: Date) -> some View {
        VStack(spacing: 0) {
            ForEach(Array(list.enumerated()), id: \.element.id) { i, s in
                let canDelete = model.canDelete(s.id, now: now)
                SwipeToDelete(id: "session.\(s.id)", enabled: canDelete, onOpen: { open = s.id }, onDelete: { toDelete = s }) {
                    row(s, now: now)
                }
                .contextMenu {
                    if canDelete { Button("Borrar sesión", systemImage: "trash", role: .destructive) { toDelete = s } }
                }
                if i < list.count - 1 { Divider().overlay(Magma.divider) }
            }
        }
        .clipShape(.rect(cornerRadius: 16)) // the swipe's red button stays inside the card's corners
        .card()
    }

    private func row(_ s: Session, now: Date) -> some View {
        let item = model.outbox.items[s.id]
        let sets = s.exercises.reduce(0) { $0 + $1.sets.working.count }
        let minutes = s.endedAt.map { Int($0.timeIntervalSince(s.startedAt) / 60) }
        return VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(s.routineTitle).font(Magma.font(16.5, .heavy, relativeTo: .headline)).foregroundStyle(Magma.text)
                Spacer()
                Text("\(Lift.dayLabel(Plan.day(s.startedAt)).lowercased()) · \(s.startedAt.formatted(date: .omitted, time: .shortened))")
                    .font(Magma.font(13, .semibold, relativeTo: .footnote)).foregroundStyle(Magma.dim)
            }
            Text([minutes.map { "\($0) min" }, "\(sets) series"].compactMap { $0 }.joined(separator: " · "))
                .font(Magma.font(13.5, relativeTo: .footnote)).foregroundStyle(Magma.dim)
            if let note = s.note {
                Label(note, systemImage: "square.and.pencil")
                    .font(Magma.font(13.5, relativeTo: .footnote)).foregroundStyle(Magma.text).lineLimit(2)
            }
            ViewThatFits(in: .horizontal) { // a narrow phone or large text: the tags go one under another
                HStack(spacing: 6) { tags(s, item: item, now: now) }
                VStack(alignment: .leading, spacing: 4) { tags(s, item: item, now: now) }
            }
            .padding(.top, 3)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 13)
        .contentShape(.rect)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private func tags(_ s: Session, item: Outbox.Item?, now: Date) -> some View {
                if model.canEdit(s.id, now: now), let end = s.endedAt {
                    EditablePill(text: "Editable hasta \(Lift.editableUntil(end: end, now: now))")
                }
                if let swap = Lift.swapTag(s) { Pill(text: swap) }
                if item?.rejected != nil {
                    Label("Rechazada", systemImage: "exclamationmark.triangle.fill")
                        .font(Magma.font(11.5, .bold, relativeTo: .caption2)).foregroundStyle(Magma.missedFg)
                } else if let item, item.session.rev > item.sentRev {
                    Pill(text: "Sin enviar")
                }
                Text("Reloj".upper).font(Magma.font(11, .bold, relativeTo: .caption2)).foregroundStyle(Magma.faint)
    }
}

/// "Push A borrada · Deshacer" for ~8 s after a delete (G91; the timer is `PhoneModel.deleteSession`'s); "Borradas"
/// in Sesiones keeps the way back after that.
private struct UndoBanner: View {
    let session: Session
    @Environment(PhoneModel.self) private var model

    var body: some View {
        HStack {
            Text("\(session.routineTitle) borrada").font(Magma.font(15, .semibold, relativeTo: .body)).foregroundStyle(Magma.text)
            Spacer()
            Button("Deshacer") { model.restoreSession(session.id) }
                .accessibilityIdentifier("undoDelete")
                .font(Magma.font(15, .bold, relativeTo: .body))
                .frame(minHeight: 44)
                .padding(.horizontal, 12)
                .contentShape(.rect)
        }
        .padding(.leading, 20)
        .padding(.trailing, 8)
        .padding(.vertical, 4)
        .glassEffect(.regular, in: .capsule) // G108: floats over the list, so it's the control layer
        .onAppear { AccessibilityNotification.Announcement(String(localized: "Sesión borrada")).post() }
    }
}

/// Swipe left on a Sesiones row (G101 c): the card stack isn't a `List`, so no `swipeActions`; this copies them. A
/// short swipe leaves "Borrar" open, a long one (past half the row) asks at once; both go through the same
/// confirmation. Vertical drags stay with the scroll view. VoiceOver: the "Borrar sesión" action. The row is a
/// button that opens the session only on a plain tap: a horizontal drag cancels it (G107 1), on any row.
private struct SwipeToDelete<Content: View>: View {
    let id: String
    let enabled: Bool
    let onOpen: () -> Void
    let onDelete: () -> Void
    @ViewBuilder let content: Content
    @State private var settled = 0.0
    @State private var width = 0.0
    /// Animated reset, so the lift glides on from where the finger left instead of snapping back first (G108).
    @GestureState(resetTransaction: Transaction(animation: .smooth(duration: 0.2))) private var drag = 0.0
    /// The last horizontal drag movement or lift. The tap and the drag's end arrive in either order, so a tap counts
    /// only when no drag is under way (`drag`, which also resets when the scroll view takes the touch) and none just ended.
    @State private var swipedAt = Date.distantPast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let x = min(0, settled + (enabled ? drag : 0))
        ZStack(alignment: .trailing) {
            if x < 0 {
                Button(role: .destructive) { close(); onDelete() } label: {
                    Label("Borrar", systemImage: "trash")
                        .labelStyle(.titleAndIcon)
                        .font(Magma.font(15, .bold, relativeTo: .body))
                        .foregroundStyle(.white)
                        .frame(width: max(Lift.SwipeEnd.button, -x))
                        .frame(maxHeight: .infinity)
                        .background(Color(rgb: 0xC62828)) // white on it 5.6:1
                }
                .buttonStyle(.plain)
                .accessibilityHidden(true) // VoiceOver uses the row's action
            }
            Button {
                guard drag == 0, Date.now.timeIntervalSince(swipedAt) > 0.5 else { return } // the end of a swipe
                if settled < 0 { close() } else { onOpen() } // with "Borrar" open, a tap closes, never opens
            } label: { content.background(Magma.card) } // opaque: the red button shows only where the row moved away
            .buttonStyle(.plain)
            .offset(x: x)
            .accessibilityIdentifier(id)
            .accessibilityActions { if enabled { Button("Borrar sesión") { onDelete() } } }
        }
        .onGeometryChange(for: Double.self) { $0.size.width } action: { width = $0 }
        .simultaneousGesture(
            DragGesture(minimumDistance: 20)
                .updating($drag) { v, state, _ in
                    if abs(v.translation.width) > abs(v.translation.height) { state = Self.dx(v) }
                }
                .onChanged { v in if abs(v.translation.width) > abs(v.translation.height) { swipedAt = .now } }
                .onEnded { v in
                    guard abs(v.translation.width) > abs(v.translation.height) else { return }
                    swipedAt = .now
                    guard enabled else { return }
                    let end = Lift.SwipeEnd(offset: settled + Self.dx(v), width: width)
                    withAnimation(reduceMotion ? nil : .smooth(duration: 0.2)) { settled = end == .open ? -Lift.SwipeEnd.button : 0 }
                    if end == .delete { onDelete() }
                })
    }

    /// The drag past its 20 pt start, so the row moves from where it is when the swipe is recognised (no jump).
    private static func dx(_ v: DragGesture.Value) -> Double {
        let w = v.translation.width
        return w > 0 ? max(0, w - 20) : min(0, w + 20)
    }

    private func close() { withAnimation(reduceMotion ? nil : .smooth(duration: 0.2)) { settled = 0 } }
}

struct Pill: View {
    let text: String
    var body: some View {
        Text(text).font(Magma.font(11.5, .bold, relativeTo: .caption2)).foregroundStyle(Magma.dim)
            .padding(.horizontal, 8).padding(.vertical, 5)
            .background(Magma.scrim, in: .rect(cornerRadius: 6))
    }
}

private struct EditablePill: View {
    let text: String
    @AppStorage("theme") private var theme = AppTheme.magenta
    var body: some View {
        Text(text).font(Magma.font(12, .bold, relativeTo: .caption)).foregroundStyle(theme.onSoft)
            .padding(.horizontal, 8).padding(.vertical, 5)
            .background(theme.soft, in: .rect(cornerRadius: 6))
    }
}
