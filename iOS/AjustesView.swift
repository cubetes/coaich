import SwiftUI
import AthleteCore

/// Ajustes (G82): Apariencia, Sonidos, Sincronización, Cuenta, versión — what the old Home held besides the plan.
/// A system sheet with a system form. Problems are a symbol plus words, never colour alone (panel lens 3).
struct AjustesView: View {
    @Environment(PhoneModel.self) private var model
    @Environment(LiveSession.self) private var live
    @Environment(\.dismiss) private var dismiss
    @AppStorage("theme") private var theme = AppTheme.magenta
    @AppStorage("cuesOn") private var cuesOn = true
    @State private var askRestart = false
    @State private var restarting = false
    @State private var restartResult: String?

    var body: some View {
        NavigationStack {
            Form {
                Section { // light/dark follows the system (ios-ui rule 12); only the accent is the app's
                    Picker("Tema", selection: $theme) {
                        Text("Magenta").tag(AppTheme.magenta)
                        Text("Neón verde").tag(AppTheme.neon)
                    }
                } header: {
                    Text("Apariencia")
                } footer: {
                    Text("Claro u oscuro sigue a Ajustes del iPhone.")
                }
                Section("Sonidos") {
                    Toggle("Sonidos en los auriculares", isOn: $cuesOn)
                    Button("Probar sonido", systemImage: "speaker.wave.2") { Task { await live.player.test() } }
                    NavigationLink("Diagnóstico de sonidos") { // G50: each cue played, or why not
                        List {
                            if live.player.log.isEmpty { Text("Sin avisos todavía").foregroundStyle(.secondary) }
                            ForEach(Array(live.player.log.enumerated()), id: \.offset) { Text($0.element).font(.caption.monospacedDigit()) }
                        }
                        .navigationTitle("Diagnóstico")
                    }
                }
                Section {
                    LabeledContent("Plan publicado", value: published ?? "—")
                    LabeledContent("Plan comprobado", value: model.lastSync.map(when) ?? "nunca")
                    if model.pendingCount > 0 { LabeledContent("Sin confirmar", value: "\(model.pendingCount)") }
                    // G107: judged by what arrived from the Watch, not only by iOS's "app installed" flag
                    LabeledContent("Reloj", value: model.watchLink == .ready ? String(localized: "Conectado") : String(localized: "No responde"))
                    LabeledContent("Último contacto del reloj", value: model.lastHeardFromWatch.map(when) ?? "—")
                    if let problem = model.watchLink.problem { Text(problem).font(.footnote).foregroundStyle(.secondary) }
                    if !model.status.isEmpty { Text(model.status).font(.footnote).foregroundStyle(.secondary) }
                    ForEach(model.outbox.rejected, id: \.session.id) { item in
                        VStack(alignment: .leading, spacing: 2) {
                            Label("Rechazada: \(item.session.routineTitle) · \(when(item.session.startedAt))",
                                  systemImage: "exclamationmark.triangle.fill")
                                .foregroundStyle(Magma.missedFg)
                            Text(item.rejected ?? "").font(.caption).foregroundStyle(.secondary)
                        }
                        .swipeActions { // G51: the only way the Watch's red "!" clears without a new rev (SY-09)
                            Button("Descartar", role: .destructive) { model.dismissRejected(item.session.id) }
                        }
                    }
                    if live.state == nil { // G98 (c): hidden while a session runs, as on the Watch
                        Button("Reiniciar conexión", systemImage: "arrow.triangle.2.circlepath") { askRestart = true }
                            .disabled(restarting)
                    }
                    if restarting { ProgressView() }
                    if let restartResult { Text(restartResult).font(.footnote).foregroundStyle(.secondary) }
                } header: {
                    Text("Sincronización")
                } footer: {
                    Text(model.outbox.rejected.isEmpty
                         ? "En este iPhone. El reloj muestra el estado de sus propias sesiones."
                         : "Desliza una rechazada para descartarla: el reloj deja de avisar. La sesión sigue guardada en el reloj.")
                }
                Section {
                    NavigationLink { GymsView() } label: {
                        LabeledContent("Gimnasios", value: model.gyms.name(model.gyms.home) ?? String(localized: "Ninguno"))
                    }
                } footer: {
                    Text("Cada sesión se guarda con su gimnasio: el coach compara las máquinas solo dentro del mismo.")
                }
                Section("Cuenta") {
                    Button("Salir", role: .destructive) { dismiss(); model.logout() }
                }
                Section {
                } footer: {
                    Text("Athlete OS \(Bundle.main.versionLabel)").frame(maxWidth: .infinity)
                }
            }
            .confirmationDialog("¿Reiniciar la conexión con el reloj?", isPresented: $askRestart, titleVisibility: .visible) {
                Button("Reiniciar conexión") {
                    restarting = true
                    restartResult = nil
                    Task { restartResult = await model.restartConnection(); restarting = false }
                }
                Button("Cancelar", role: .cancel) {}
            } message: {
                Text("Vuelve a conectar con el reloj, le reenvía el plan y envía las sesiones pendientes. No borra nada. Si el iPhone no ve la app del reloj, esto no lo arregla: reinstala las dos apps juntas desde el Mac, sin borrarlas antes (borrarlas pierde lo no enviado).")
            }
            .navigationTitle("Ajustes")
            .onAppear { model.updateWatchLink() } // old evidence expires (15 min) without a refresh
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("OK") { dismiss() } }
            }
        }
    }

    private var published: String? {
        UserDefaults.standard.string(forKey: "publishedAt").flatMap { try? Date($0, strategy: .iso8601) }.map(when)
    }

    /// "hoy 07:12" / "9 oct 07:12".
    private func when(_ d: Date) -> String {
        let time = d.formatted(date: .omitted, time: .shortened)
        return Calendar.current.isDateInToday(d) ? "hoy \(time)" : "\(Lift.short(Plan.day(d))) \(time)"
    }
}

/// Ajustes › Gimnasios (G92, G111): the list, the habitual gym and the "more than one gym" switch. Off = every session
/// gets the habitual gym and the Watch shows nothing about gyms; on = the Watch's routine list offers "Gimnasio: X".
private struct GymsView: View {
    @Environment(PhoneModel.self) private var model
    @State private var newName = ""
    @State private var askHome: Gyms.Gym?
    /// Switch turned off with more than one gym: which one from now on.
    @State private var askFinal = false

    var body: some View {
        Form {
            Section {
                Toggle("Entreno en más de un gimnasio", isOn: Binding(get: { model.gyms.multi },
                                                                   set: { on in
                    if !on && model.gyms.list.count > 1 { askFinal = true } else { model.updateGyms { $0.multi = on } }
                }))
            } footer: {
                Text(model.gyms.multi
                     ? "El reloj muestra el gimnasio antes de empezar; por defecto, el de la última sesión."
                     : "Todas las sesiones se guardan en tu gimnasio habitual.")
            }
            Section {
                ForEach(model.gyms.list) { gym in
                    Button {
                        if gym.id != model.gyms.home { askHome = gym }
                    } label: {
                        LabeledContent(gym.name) {
                            if gym.id == model.gyms.home { Label("Habitual", systemImage: "checkmark").labelStyle(.titleAndIcon) }
                        }
                    }
                    .foregroundStyle(.primary)
                    .accessibilityHint(gym.id == model.gyms.home ? "" : String(localized: "Hacerlo tu gimnasio habitual"))
                    .deleteDisabled(gym.id == model.gyms.home)
                }
                .onDelete { rows in
                    let ids = rows.map { model.gyms.list[$0].id }
                    model.updateGyms { g in ids.forEach { g.remove($0) } }
                }
                HStack {
                    TextField("Nuevo gimnasio", text: $newName).submitLabel(.done).onSubmit(add)
                    Button("Añadir", action: add).disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            } header: {
                Text("Tus gimnasios")
            } footer: {
                Text("Toca uno para hacerlo habitual. El habitual no se puede borrar.")
            }
        }
        .navigationTitle("Gimnasios")
        .confirmationDialog("¿En qué gimnasio entrenas a partir de ahora?", isPresented: $askFinal, titleVisibility: .visible) {
            ForEach(model.gyms.list) { gym in
                Button(gym.id == model.gyms.home ? "\(gym.name) (habitual)" : gym.name) { model.updateGyms { $0.settle(on: gym.id) } }
            }
            Button("Cancelar", role: .cancel) {}
        } message: {
            Text("Todas las sesiones nuevas se guardan en ese gimnasio. Los demás siguen en la lista. Si no es el habitual, las máquinas se recalibran.")
        }
        .alert("¿Desde hoy entrenas aquí?", isPresented: Binding(get: { askHome != nil }, set: { if !$0 { askHome = nil } }),
               presenting: askHome) { gym in
            Button("Sí, es mi gimnasio habitual") { model.updateGyms { $0.home = gym.id } }
            Button("Cancelar", role: .cancel) {}
        } message: { _ in
            Text("Las máquinas se recalibran en el nuevo gimnasio.")
        }
    }

    private func add() {
        let name = newName
        model.updateGyms { $0.add(name) }
        newName = ""
    }
}
