import Charts
import SwiftUI
import UIKit
import AthleteCore

/// The exercise guide (G82 Guía A, G84): always the same order — "Objetivo · Últ." under the title, photos (only
/// when the snapshot's entry has `images`, EN-20), Claves del coach (+ Tu nota), Cómo se hace, Errores comunes, the
/// objective card, Por qué, Músculos, Tu progreso (this slot's own trend: one routine, one rep range). ↑ ↓ walk the
/// routine in place and scroll back to the top.
struct GuideView: View {
    let routineKey: String
    let slots: [String]
    @State var current: String
    @Environment(PhoneModel.self) private var model
    @AppStorage("theme") private var theme = AppTheme.magenta
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    init(routineKey: String, slots: [String], current: String) {
        self.routineKey = routineKey
        self.slots = slots
        _current = State(initialValue: current)
    }

    var body: some View {
        let e = model.entreno?.payload.workout
        let index = slots.firstIndex(of: current) ?? 0
        ScrollViewReader { proxy in
            ScrollView {
                if let slot = e?.slots?[current] {
                    page(slot, guide: slot.slug.flatMap { e?.guide?[$0] }, index: index, targets: e?.meta?.targetsStatus,
                         routine: e?.routines?[routineKey]?.title ?? "")
                        .id(current)
                        .transition(.opacity)
                } else {
                    ContentUnavailableView("Ejercicio no encontrado", systemImage: "questionmark")
                }
            }
            .background(Magma.bg)
            .onChange(of: current) { proxy.scrollTo(current, anchor: .top) }
        }
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button { go(index - 1) } label: { Image(systemName: "chevron.up") }
                    .accessibilityLabel("Ejercicio anterior").disabled(index == 0)
                Button { go(index + 1) } label: { Image(systemName: "chevron.down") }
                    .accessibilityLabel("Ejercicio siguiente").disabled(index >= slots.count - 1)
            }
        }
    }

    private func go(_ i: Int) {
        guard slots.indices.contains(i) else { return }
        withAnimation(reduceMotion ? nil : .smooth(duration: 0.2)) { current = slots[i] }
    }

    private func page(_ slot: Entreno.Slot, guide: Entreno.Guide?, index: Int, targets: String?, routine: String) -> some View {
        let status = Lift.status(slot.target, targets: targets)
        let change = Lift.changeWord(slot.target, status: status)
        let coach = Lift.cueBullets(slot.cueEs) + [guide?.setupEs].compactMap { $0 }
        let personal = (guide?.personalEs ?? []).filter { !$0.isEmpty }
        let steps = (guide?.stepsEs ?? []).filter { !$0.isEmpty }
        let mistakes = (guide?.mistakesEs ?? []).filter { !$0.isEmpty }
        let name = guide?.nameEs ?? slot.name
        return VStack(alignment: .leading, spacing: 0) {
            Text("\(routine) · \(index + 1) de \(slots.count)".upper)
                .font(Magma.font(12.5, .bold, relativeTo: .caption)).kerning(0.7).foregroundStyle(Magma.dim)
            Text(name).font(Magma.font(28, .heavy, relativeTo: .title)).foregroundStyle(Magma.text)
                .accessibilityAddTraits(.isHeader).padding(.top, 2)
            Text(Lift.objectiveLine(slot)).font(Magma.font(15, .semibold, relativeTo: .subheadline)).foregroundStyle(Magma.dim)
                .padding(.top, 6)

            if let images = guide?.images, let start = Photo.image(images.start), let end = Photo.image(images.end) {
                HStack(spacing: 8) {
                    Photo(image: start, caption: "Inicio", spoken: "\(name), posición inicial")
                    Photo(image: end, caption: "Final", spoken: "\(name), posición final")
                }
                .padding(.top, 14)
            }

            if !coach.isEmpty || !personal.isEmpty {
                SectionLabel(text: "Claves del coach")
                if !coach.isEmpty { bullets(coach).card() }
                if !personal.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Label("Tu nota", systemImage: "note.text").font(Magma.font(13, .bold, relativeTo: .footnote)).foregroundStyle(theme.onSoft)
                        bullets(personal, padded: false)
                    }
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(theme.soft, in: .rect(cornerRadius: 16))
                    .padding(.top, 8)
                }
            }
            if !steps.isEmpty {
                SectionLabel(text: "Cómo se hace")
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(steps.enumerated()), id: \.offset) { i, step in
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Text("\(i + 1)").font(Magma.font(14.5, .heavy, relativeTo: .body)).foregroundStyle(theme.tint)
                            Text(step).font(Magma.font(14.5, relativeTo: .body)).foregroundStyle(Magma.text).fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                .padding(14).frame(maxWidth: .infinity, alignment: .leading).card()
            }
            if !mistakes.isEmpty {
                SectionLabel(text: "Errores comunes")
                bullets(mistakes).card()
            }

            objectiveCard(slot, status: status, change: change).padding(.top, 20)

            if let why = guide?.whyInPlanEs {
                SectionLabel(text: "Por qué está en tu plan")
                Text(why).font(Magma.font(14.5, relativeTo: .body)).foregroundStyle(Magma.text)
                    .padding(14).frame(maxWidth: .infinity, alignment: .leading).card()
            }
            let primary = guide?.muscles?.primary ?? [], secondary = guide?.muscles?.secondary ?? []
            if !primary.isEmpty || !secondary.isEmpty {
                SectionLabel(text: "Músculos")
                VStack(alignment: .leading, spacing: 4) {
                    if !primary.isEmpty { Text("Principales: \(primary.joined(separator: ", "))").font(Magma.font(14.5, .bold, relativeTo: .body)) }
                    if !secondary.isEmpty { Text("Secundarios: \(secondary.joined(separator: ", "))").font(Magma.font(14.5, relativeTo: .body)) }
                }
                .foregroundStyle(Magma.text).padding(14).frame(maxWidth: .infinity, alignment: .leading).card()
            }
            if let trend = slot.trend, slot.assisted != true { // assisted: the logged weight is help, not strength
                SectionLabel(text: "Tu progreso · \(routine)")
                TrendCard(trend: trend)
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 8)
        .padding(.bottom, 32)
    }

    private func bullets(_ items: [String], padded: Bool = true) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, t in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("•").foregroundStyle(theme.tint).accessibilityHidden(true)
                    Text(t).foregroundStyle(Magma.text).fixedSize(horizontal: false, vertical: true) // wrap, never cut
                }
                .font(Magma.font(14.5, relativeTo: .body))
            }
        }
        .padding(padded ? 14 : 0)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func objectiveCard(_ slot: Entreno.Slot, status: Lift.Status?, change: String?) -> some View {
        let p = slot.prescription
        let stalled = slot.flags?.contains("stalled") == true
        let pill = status.flatMap { $0 == .auto ? nil : Lift.label($0) } // "Actualizado automáticamente" isn't shown
        return VStack(alignment: .leading, spacing: 6) {
            Text("Objetivo".upper).font(Magma.font(12, .heavy, relativeTo: .caption)).kerning(0.8).foregroundStyle(Magma.dim)
            Text(Lift.objective(slot.target) ?? "Sin objetivo publicado").font(Magma.font(26, .black, relativeTo: .title2)).foregroundStyle(Magma.text)
            if change != nil || pill != nil || stalled || slot.assisted == true {
                HStack(spacing: 6) {
                    if let change {
                        Text(change).font(Magma.font(13, .heavy, relativeTo: .footnote))
                            .foregroundStyle(slot.target?.decision == "increase" ? AnyShapeStyle(theme.tint) : AnyShapeStyle(Magma.dim))
                    }
                    if let pill { Pill(text: pill) }
                    if stalled { Pill(text: "Estancado") }
                    if slot.assisted == true { Pill(text: "Asistido") }
                }
            }
            Text([p?.sets.map { "\($0) series" }, p?.repRange.map { "\(Lift.reps($0)) reps" }, Lift.rest(p?.restS).map { "descanso \($0)" }]
                .compactMap { $0 }.joined(separator: " · "))
                .font(Magma.font(13.5, relativeTo: .footnote)).foregroundStyle(Magma.dim)
            if status == .pending, let t = slot.target {
                Text("Propuesta del check-in: \(t.changeEs ?? t.decision.flatMap { Lift.decision[$0] } ?? ""). Se aplica cuando des tu OK al coach; hasta entonces, el objetivo es el de la semana pasada.")
                    .font(Magma.font(13.5, relativeTo: .footnote)).foregroundStyle(Magma.text)
            }
            if status == .rejected {
                Text("No aceptaste la propuesta del check-in: se mantiene el objetivo.").font(Magma.font(13.5, relativeTo: .footnote))
            }
            if slot.assisted == true {
                Text("Ejercicio asistido: menos ayuda es más difícil.").font(Magma.font(13.5, relativeTo: .footnote))
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .card()
        .accessibilityElement(children: .combine)
    }
}

/// A bundled exercise photo (the web's `exercise-img`, copied into the app). The path is the snapshot's, so a photo
/// shows only for an entry that names one; a missing file shows nothing.
private struct Photo: View {
    let image: UIImage
    let caption: String
    let spoken: String

    static func image(_ webPath: String) -> UIImage? {
        guard let base = Bundle.main.resourceURL else { return nil }
        let path = webPath.hasPrefix("/") ? String(webPath.dropFirst()) : webPath
        return UIImage(contentsOfFile: base.appending(path: path).path(percentEncoded: false))
    }

    var body: some View {
        Image(uiImage: image)
            .resizable()
            .aspectRatio(3 / 2, contentMode: .fill)
            .frame(maxWidth: .infinity)
            .clipShape(.rect(cornerRadius: 12))
            .overlay(alignment: .bottomLeading) {
                Text(caption.upper).font(Magma.font(11, .bold, relativeTo: .caption2))
                    .foregroundStyle(.white).padding(.horizontal, 6).padding(.vertical, 4)
                    .background(.black.opacity(0.6), in: .rect(cornerRadius: 5)).padding(8)
                    .accessibilityHidden(true)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(spoken)
            .accessibilityAddTraits(.isImage)
    }
}

/// The publisher's trend for this slot, as published: calibrating → its words; ok → the latest value, change and verdict,
/// and the points with the ± band around the latest one.
private struct TrendCard: View {
    let trend: Entreno.Trend
    @AppStorage("theme") private var theme = AppTheme.magenta

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if trend.status == "ok", let verdict = trend.verdict {
                let last = trend.points?.last
                HStack(alignment: .firstTextBaseline) {
                    if let last {
                        Text(Lift.num(last.value)).font(Magma.font(26, .black, relativeTo: .title2))
                        Text("kg · \(trend.metric == "load_at_floor" ? "peso con el mínimo de reps" : "fuerza estimada")")
                            .font(Magma.font(13, relativeTo: .footnote)).foregroundStyle(Magma.dim)
                    }
                    Spacer()
                    Text([trend.deltaPct.map(Lift.pct), verdict].compactMap { $0 }.joined(separator: " · "))
                        .font(Magma.font(14, .heavy, relativeTo: .subheadline))
                        .foregroundStyle(verdict == "sube" ? AnyShapeStyle(theme.tint) : verdict == "baja" ? AnyShapeStyle(Magma.cautionFg) : AnyShapeStyle(Magma.dim))
                }
                if let pts = trend.points, pts.count >= 2 {
                    Chart {
                        if let v = pts.last?.value, let band = trend.bandPct {
                            RectangleMark(xStart: .value("Inicio", 0), xEnd: .value("Fin", pts.count - 1),
                                          yStart: .value("Bajo", v * (1 - band / 100)), yEnd: .value("Alto", v * (1 + band / 100)))
                                .foregroundStyle(theme.soft)
                        }
                        ForEach(Array(pts.enumerated()), id: \.offset) { i, p in
                            LineMark(x: .value("Sesión", i), y: .value("kg", p.value)).foregroundStyle(theme.tint)
                        }
                    }
                    .chartXAxis(.hidden)
                    .chartYScale(domain: .automatic(includesZero: false))
                    .frame(height: 110)
                    .accessibilityLabel("Tendencia de \(Lift.short(pts[0].date)) a \(Lift.short(pts[pts.count - 1].date)): \(Lift.num(pts[0].value)) a \(Lift.num(pts[pts.count - 1].value)) kilos")
                    Text("\(Lift.short(pts[0].date)) – \(Lift.short(pts[pts.count - 1].date)) · banda ±\(Lift.num(trend.bandPct ?? 0)) %")
                        .font(Magma.font(12, relativeTo: .caption)).foregroundStyle(Magma.faint)
                }
            } else {
                Text(Lift.calibrating(trend)).font(Magma.font(15, .bold, relativeTo: .body))
                Text("Para saber si subes hacen falta \(Lift.trendMinSessions) entrenos de este ejercicio en esta rutina, repartidos en al menos \(Lift.trendMinWeeks) semanas. Llevas \(trend.weeks ?? 0) \(trend.weeks == 1 ? "semana" : "semanas").")
                    .font(Magma.font(13.5, relativeTo: .footnote)).foregroundStyle(Magma.dim)
            }
        }
        .foregroundStyle(Magma.text)
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .card()
    }
}
