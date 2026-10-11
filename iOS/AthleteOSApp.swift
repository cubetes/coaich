import SwiftUI
import AthleteCore

@main
struct AthleteOSApp: App {
    @State private var model = PhoneModel()
    @State private var live = LiveSession() // created at launch: it registers the mirroring handler
    @AppStorage("theme") private var theme = AppTheme.magenta

    var body: some Scene {
        WindowGroup {
            Group {
                if model.token == nil { LoginView() } else { RootView() }
            }
            .tint(theme.tint)
            .onChange(of: live.heardAt) { _, at in if let at { model.heardFromWatch(at: at) } } // G107: link evidence
        }
        .environment(model)
        .environment(live)
    }
}

/// Phase 0 shell (G82 "S0"): Entreno is the whole app, the settings button opens Ajustes. Everything that must work
/// whichever screen or sheet is showing lives here, never inside a screen (red team EN-01/EN-02): the refresh, the G59
/// re-link and HealthKit's ask on every return to the foreground, and the Watch's "Otro" picker — presented over
/// Ajustes when Ajustes is open (one view can't present two sheets), from here otherwise.
struct RootView: View {
    @Environment(PhoneModel.self) private var model
    @Environment(LiveSession.self) private var live
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("theme") private var theme = AppTheme.magenta
    @State private var showAjustes = false

    var body: some View {
        NavigationStack { EntrenoView(showAjustes: $showAjustes) }
            .sheet(isPresented: $showAjustes) {
                AjustesView()
                    .sheet(item: swap(inAjustes: true)) { SwapPicker(request: $0).tint(theme.tint) }
                    .tint(theme.tint)
            }
            .sheet(item: swap(inAjustes: false)) { SwapPicker(request: $0).tint(theme.tint) }
            .onChange(of: theme) { model.sendContextToWatch() }
            .task(id: scenePhase) {
                guard scenePhase == .active else { return }
                #if DEBUG
                if UITestFixture.isOn { return } // no HealthKit sheet, no Watch re-link in UI tests
                #endif
                live.appBecameActive()
                await live.requestAuthorization() // asks once; lean: assumed needed for mirroring (Apple's sample asks on both devices), unproven
                await model.refresh()
            }
    }

    /// The swap request, shown by exactly one presenter: the Ajustes sheet while it is open, the root otherwise.
    private func swap(inAjustes: Bool) -> Binding<PhoneModel.SwapRequest?> {
        Binding(get: { showAjustes == inAjustes ? model.swapRequest : nil }, set: { model.swapRequest = $0 })
    }
}

struct LoginView: View {
    @Environment(PhoneModel.self) private var model
    @State private var email = ""
    @State private var password = ""
    @State private var busy = false

    var body: some View {
        NavigationStack {
            Form {
                TextField("Email", text: $email)
                    .textContentType(.username)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                SecureField("Contraseña", text: $password)
                    .textContentType(.password)
                Button("Entrar") {
                    busy = true
                    Task { await model.login(email: email, password: password); busy = false }
                }
                .disabled(busy || email.isEmpty || password.isEmpty)
                if !model.status.isEmpty { Text(model.status).foregroundStyle(.red) }
                Text(Bundle.main.versionLabel).font(.caption).foregroundStyle(.secondary)
            }
            .navigationTitle("Athlete OS")
        }
    }
}

