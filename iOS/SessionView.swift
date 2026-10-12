import SwiftUI
import AthleteCore

/// The last finished session, read-only or in edit mode (G70, option A): kg, reps, type, RIR, delete, add a set;
/// Guardar = one new rev. Editable only after the Watch's final rev and up to 24 h after the end.
struct SessionView: View {
    @Environment(PhoneModel.self) private var model
    let id: String
    /// Edit mode's working copy; nil = read view. Nothing is written until Guardar (red team ED-11).
    @State private var draft: Session?
    @State private var askDiscard = false
    @State private var deleteAll: (slot: String, index: Int)?
    @State private var askDelete: Session?
    @Environment(\.dismiss) private var dismiss
    @AppStorage("theme") private var theme = AppTheme.magenta

    private var held: Session? { model.outbox.items[id]?.session }
    /// Sets or the note (G78, compared the way `setNote` will store it: a trailing space alone changes nothing).
    private var changed: Bool {
        guard let d = draft, let h = held else { return false }
        var probe = h
        probe.setNote(d.note)
        return d.exercises != h.exercises || probe.note != h.note
    }

    var body: some View {
        if let s = draft ?? held {
            List {
                Section {
                    if draft != nil {
                        Text("Una serie nueva copia la anterior. Guardar envía la sesión corregida al servidor y al reloj.")
                    } else {
                        Text(rule(s)).foregroundStyle(.secondary)
                    }
                }
                if draft != nil { // G78: the note, saved with Guardar in the same rev
                    Section {
                        TextField("Nota", text: Binding(get: { draft?.note ?? "" }, set: { draft?.note = $0 }), axis: .vertical)
                            .lineLimit(3...8)
                    } header: {
                        Text("Nota")
                    } footer: {
                        if (draft?.note?.unicodeScalars.count ?? 0) > Session.maxNote {
                            Text("Se guardan los primeros \(Session.maxNote) caracteres.").foregroundStyle(.red)
                        }
                    }
                } else if let note = s.note {
                    Section("Nota") { Text(note) }
                }
                ForEach(s.slotGroups, id: \.slot) { group in
                    Section(model.plan?.slots[group.slot]?.name ?? s.exercises[group.entries[0].position].title) {
                        ForEach(group.entries, id: \.position) { entry in
                            entryRows(s, group, entry)
                        }
                    }
                }
                if draft == nil, model.canDelete(id) { // G91: its own section, last, away from the sets
                    Section {
                        Button("Borrar sesión", systemImage: "trash", role: .destructive) { askDelete = s }
                            .accessibilityIdentifier("deleteSession")
                    }
                }
            }
            .deleteSessionDialog($askDelete) { model.deleteSession($0.id); dismiss() } // on the List: the row is lazy
            .navigationTitle(s.routineTitle)
            .navigationBarTitleDisplayMode(.inline)
            .navigationBarBackButtonHidden(draft != nil)
            .toolbar {
                if draft != nil {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Cancelar") { if changed { askDiscard = true } else { draft = nil } }
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        // A filled tint button, so its label can follow G75 (black on the lime, never white).
                        Button { if let d = draft { model.saveEdit(d) }; draft = nil } label: { // no rev when it ends unchanged
                            Text("Guardar").bold().foregroundStyle(changed ? AnyShapeStyle(theme.onTint) : AnyShapeStyle(.secondary))
                        }
                        .buttonStyle(.glassProminent)
                        .disabled(!changed)
                    }
                } else if model.canEdit(id) {
                    ToolbarItem(placement: .primaryAction) { // the 24 h window is checked here; a save started inside it counts
                        Button("Editar") { draft = held }
                    }
                }
            }
            .confirmationDialog("¿Descartar cambios?", isPresented: $askDiscard, titleVisibility: .visible) {
                Button("Descartar cambios", role: .destructive) { draft = nil }
                Button("Seguir editando", role: .cancel) {}
            }
            .confirmationDialog("Se borran todas las series de la sesión.",
                                isPresented: Binding(get: { deleteAll != nil }, set: { if !$0 { deleteAll = nil } }),
                                titleVisibility: .visible) {
                Button("Borrar", role: .destructive) {
                    if let d = deleteAll { draft?.deleteSet(slot: d.slot, index: d.index) }
                }
                Button("Cancelar", role: .cancel) {}
            }
        } else {
            ContentUnavailableView("Sesión no encontrada", systemImage: "questionmark")
        }
    }

    /// One exercise entry of a slot: its "⇄" line after a swap, its sets, and "Añadir serie" on the slot's last entry
    /// only (never on a swapped slot's original exercise).
    @ViewBuilder
    private func entryRows(_ s: Session, _ group: Session.SlotGroup, _ entry: Session.SlotGroup.Entry) -> some View {
        let ex = s.exercises[entry.position]
        if ex.substituted || group.entries.count > 1 {
            VStack(alignment: .leading) {
                Text(ex.substituted ? "⇄ \(ex.title)" : ex.title).font(.subheadline.weight(.semibold))
                if ex.substituted, let planned = model.plan?.slots[group.slot] {
                    Text("en vez de \(planned.shortName ?? planned.name)").font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        ForEach(ex.sets.indices, id: \.self) { j in
            SetRow(set: ex.sets[j], number: entry.offset + j + 1, edit: draft == nil ? nil : binding(group.slot, entry.offset + j))
        }
        .onDelete(perform: draft == nil ? nil : { delete(group.slot, entry.offset, $0) })
        if draft != nil, entry == group.entries.last, let last = ex.sets.last {
            Button("Añadir serie", systemImage: "plus") {
                draft?.addSet(exercise: entry.position, weightKg: last.weightKg, reps: last.reps, type: last.type, at: last.doneAt)
            }
            .disabled(ex.sets.count >= Session.maxSets)
        }
    }

    private func rule(_ s: Session) -> String {
        guard let end = s.endedAt else { return "" }
        if model.canEdit(id) { return "Puedes editarla hasta \(Lift.editableUntil(end: end, now: .now))." } // panel copy: one verb
        if Date.now.timeIntervalSince(end) > Session.editWindow {
            return "🔒 Bloqueada. Las sesiones se pueden editar hasta 24 h después de terminar."
        }
        return "Esperando al reloj… Podrás corregirla cuando el reloj termine de enviarla."
    }

    private func delete(_ slot: String, _ offset: Int, _ offsets: IndexSet) {
        let total = draft?.exercises.reduce(0) { $0 + $1.sets.count } ?? 0
        if offsets.count >= total, let j = offsets.first { return deleteAll = (slot, offset + j) } // must-fix 21: ask first
        for j in offsets.sorted(by: >) { draft?.deleteSet(slot: slot, index: offset + j) }
    }

    /// Writes through `Session`'s own edits: bounds checked there, `unedited` cleared on a kg/reps change.
    private func binding(_ slot: String, _ index: Int) -> Binding<Session.SetEntry>? {
        guard let set = draft?.sets(forSlot: slot)[safe: index] else { return nil }
        return Binding(get: { draft?.sets(forSlot: slot)[safe: index] ?? set }, set: { new in
            let kg = (new.weightKg * 100).rounded() / 100 // the contract's ≤ 2 decimals
            draft?.editSet(slot: slot, index: index, weightKg: kg, reps: new.reps, type: new.type)
            draft?.setRIR(new.rir, slot: slot, index: index)
        })
    }
}

/// One set: "1 · 100 kg × 8 · RIR 2" to read; in edit mode its type menu, kg × reps fields and RIR menu.
/// Stacks at accessibility text sizes (panel must-fix 24).
private struct SetRow: View {
    let set: Session.SetEntry
    let number: Int
    let edit: Binding<Session.SetEntry>?
    @Environment(\.dynamicTypeSize) private var size

    var body: some View {
        let layout = size.isAccessibilitySize ? AnyLayout(VStackLayout(alignment: .leading)) : AnyLayout(HStackLayout())
        layout {
            Text("\(number)").monospacedDigit().foregroundStyle(.secondary)
            if let edit {
                Menu(set.type.label) {
                    Picker("Tipo", selection: edit.type) {
                        ForEach([Session.SetType.warmup, .normal, .failure, .dropset], id: \.self) { Text($0.label).tag($0) }
                    }
                }
                NumberField(label: "kg", value: edit.weightKg, valid: Entry.kg).frame(minWidth: 56)
                Text("×")
                NumberField(label: "reps", value: Binding(get: { Double(edit.wrappedValue.reps) },
                                                          set: { edit.wrappedValue.reps = Int($0) }),
                            valid: Double(Entry.reps.lowerBound)...Double(Entry.reps.upperBound), whole: true)
                    .frame(minWidth: 36)
                Spacer()
                Menu(set.rir.map { "RIR \($0 == 3 ? "3+" : "\($0)")" } ?? "RIR —") {
                    Picker("RIR", selection: edit.rir) {
                        Text("—").tag(Int?.none)
                        ForEach(0..<4) { Text($0 == 3 ? "3+" : "\($0)").tag(Int?.some($0)) }
                    }
                }
            } else {
                if set.type != .normal { Text(set.type.label).font(.caption.weight(.semibold)).foregroundStyle(.tint) }
                Text("\(set.weightKg.formatted()) kg × \(set.reps)").monospacedDigit()
                Spacer()
                if let rir = set.rir { Text("RIR \(rir == 3 ? "3+" : "\(rir)")").foregroundStyle(.secondary) }
            }
        }
        .textFieldStyle(.roundedBorder)
    }
}

/// A kg or reps field that writes on every keystroke (red team re-check RC-02): `TextField(value:format:)` only
/// commits on Return or focus loss, the number pads have no Return, and Guardar doesn't take the focus — so the value
/// being typed was silently dropped. Out of range or unparsable: red, and not written (the old value stays).
private struct NumberField: View {
    let label: String
    @Binding var value: Double
    let valid: ClosedRange<Double>
    var whole = false
    @State private var text = ""

    var body: some View {
        TextField(label, text: $text)
            .keyboardType(whole ? .numberPad : .decimalPad)
            .foregroundStyle(parsed == nil ? .red : .primary)
            .onAppear { text = Self.show(value) }
            .onChange(of: value) { _, v in if parsed != v { text = Self.show(v) } } // a delete moved another set here
            .onChange(of: text) { if let v = parsed, v != value { value = v } }
            .accessibilityLabel(label)
    }

    /// "102,5" or "102.5"; at most 2 decimals (the contract), whole for reps.
    private var parsed: Double? {
        guard let v = Double(text.replacingOccurrences(of: ",", with: ".")), valid.contains(v),
              whole ? v == v.rounded() : (v * 100 - (v * 100).rounded()).magnitude < 1e-6 else { return nil }
        return v
    }

    private static func show(_ v: Double) -> String { v.formatted(.number.grouping(.never)) }
}

private extension Session.SetType {
    var label: String {
        switch self {
        case .warmup: "Calentamiento"
        case .normal: "Normal"
        case .failure: "Fallo"
        case .dropset: "Drop"
        }
    }
}

private extension Array {
    subscript(safe i: Int) -> Element? { indices.contains(i) ? self[i] : nil }
}

extension View {
    /// "Borrar sesión" confirmation (G91), shared by SessionView and the Sesiones row's swipe and menu: names routine,
    /// day and working sets; Cancelar is the safe default. A short sheet that slides up from the bottom (G107 4), not a
    /// popover; `delete` runs once the sheet has gone, so SessionView can pop back without a sheet still on it.
    func deleteSessionDialog(_ session: Binding<Session?>, delete: @escaping (Session) -> Void) -> some View {
        modifier(DeleteSessionSheet(session: session, delete: delete))
    }
}

private struct DeleteSessionSheet: ViewModifier {
    @Binding var session: Session?
    let delete: (Session) -> Void
    @State private var confirmed: Session?
    @State private var height = 320.0

    func body(content: Content) -> some View {
        content.sheet(item: $session, onDismiss: {
            if let s = confirmed { confirmed = nil; delete(s) }
        }) { s in
            ScrollView { // at the largest text sizes the sheet grows to full height and scrolls
                VStack(spacing: 16) {
                    Text("¿Borrar la sesión?").font(.headline).accessibilityAddTraits(.isHeader)
                    Text(message(s)).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    VStack(spacing: 10) {
                        Button(role: .destructive) { confirmed = s; session = nil } label: {
                            Text("Borrar sesión").bold().frame(maxWidth: .infinity, minHeight: 44)
                        }
                        .buttonStyle(.borderedProminent).tint(Color(rgb: 0xC62828)) // white on it 5.6:1
                        .accessibilityIdentifier("confirmDeleteSession")
                        Button { session = nil } label: {
                            Text("Cancelar").frame(maxWidth: .infinity, minHeight: 44)
                        }
                        .buttonStyle(.bordered)
                        .keyboardShortcut(.defaultAction)
                    }
                    .buttonBorderShape(.capsule)
                }
                .padding(.horizontal, 20)
                .padding(.top, 28)
                .padding(.bottom, 12)
                .onGeometryChange(for: Double.self) { $0.size.height } action: { height = $0 }
            }
            .scrollBounceBehavior(.basedOnSize)
            .presentationDetents([.height(height)])
            .presentationDragIndicator(.visible)
        }
    }

    private func message(_ s: Session) -> AttributedString {
        let sets = s.exercises.reduce(0) { $0 + $1.sets.working.count }
        return AttributedString(localized: "Se borra \(s.routineTitle) del \(s.startedAt, format: .dateTime.weekday(.abbreviated).day().month(.abbreviated)) · ^[\(sets) serie](inflect: true). Sale del historial y de la revisión del coach. El entreno sigue en Salud.")
    }
}

/// "Otro (en el iPhone)" (G69): every plan exercise, the coach's alternatives for the slot first. Picking one answers
/// the Watch; Cancelar answers nothing.
struct SwapPicker: View {
    @Environment(PhoneModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let request: PhoneModel.SwapRequest
    @State private var query = ""
    /// G73 muscle chip; nil = Todos.
    @State private var group: MuscleGroup?
    @AppStorage("theme") private var theme = AppTheme.magenta

    var body: some View {
        let choices = model.plan?.swapChoices(slot: request.slot) ?? (coach: [], plan: [])
        let chips = MuscleGroup.chips(for: choices.coach + choices.plan) // none from a snapshot without muscles
        let match = { (c: Plan.Choice) in
            (query.isEmpty || c.name.localizedStandardContains(query)) && (group == nil || c.group == group)
        }
        NavigationStack {
            List {
                Section {
                    Text("En el reloj: \(request.exercise.isEmpty ? model.plan?.slots[request.slot]?.name ?? "" : request.exercise)")
                    if let n = request.setNumber, let of = request.sets { Text("Serie \(n)/\(of)").foregroundStyle(.secondary) }
                }
                if !chips.isEmpty {
                    ScrollView(.horizontal) {
                        HStack(spacing: 8) {
                            chip("Todos", nil)
                            ForEach(chips, id: \.self) { chip($0.label, $0) }
                        }
                    }
                    .scrollIndicators(.hidden)
                    .listRowInsets(EdgeInsets(top: 4, leading: 16, bottom: 4, trailing: 16))
                    .listRowBackground(Color.clear)
                }
                let coach = choices.coach.filter(match), rest = choices.plan.filter(match)
                if !coach.isEmpty { Section("Del coach") { rows(coach) } } // a chip can empty a section: no bare header
                if !rest.isEmpty { Section("En tu plan") { rows(rest) } }
            }
            .searchable(text: $query, prompt: "Buscar")
            .navigationTitle("Cambiar ejercicio")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancelar") { model.swapRequest = nil; dismiss() } }
            }
        }
    }

    /// Selected: the tint fill with its G75 label (black on the lime); others: grey fill, primary label.
    private func chip(_ label: String, _ g: MuscleGroup?) -> some View {
        let on = group == g
        return Button { group = g } label: {
            Text(label).font(.subheadline.weight(.bold)) // bold ≥ 15 pt on the accent fill (white on #FF3D6E is 3.4:1)
                .foregroundStyle(on ? AnyShapeStyle(theme.onTint) : AnyShapeStyle(.primary))
                .padding(.horizontal, 14).frame(minHeight: 44)
                .background(on ? AnyShapeStyle(.tint) : AnyShapeStyle(.fill.tertiary), in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    private func rows(_ list: [Plan.Choice]) -> some View {
        ForEach(list, id: \.templateId) { c in
            Button(c.name) { model.answerSwap(c); dismiss() }
        }
    }
}
