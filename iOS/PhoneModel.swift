import Foundation
import Network
import Security
import UIKit
import WatchConnectivity
import AthleteCore

/// The phone's whole job in M1: log in, read the published plan, hand it to the Watch,
/// and relay the Watch's session documents to the Worker without ever losing one.
@Observable
final class PhoneModel: NSObject {
    var token: String? = Keychain.read()
    var plan: Plan?
    /// The same snapshot read for the iPhone's Entreno (G82): coach words, grades, guide. Never sent to the Watch.
    var entreno: EntrenoSnapshot?
    /// How the last refresh went; anything but `.ok` is Entreno's freshness line (EN-09/EN-12), the cached plan stays.
    var lastRefresh = Lift.Refresh.ok
    /// The server's snapshot has a schema major this build can't read: the screens ask to update the app.
    var unsupported: Bool { lastRefresh == .unsupported }
    var lastSync = UserDefaults.standard.object(forKey: "lastSync") as? Date
    var status = ""
    private(set) var outbox = Outbox()
    /// Ajustes › Gimnasios (G92, G111); the Watch gets a copy in the application context.
    private(set) var gyms = (UserDefaults.standard.data(forKey: "gyms")).flatMap { try? JSONDecoder().decode(Gyms.self, from: $0) } ?? Gyms()
    private var flushing = false
    /// The Watch asked for "Otro (en el iPhone)" (G69); the swap picker shows while set. The latest request wins.
    var swapRequest: SwapRequest?
    /// The session just deleted (G91): Sesiones offers "Deshacer" for ~8 s.
    var justDeleted: String?
    /// What WatchConnectivity says about the Watch app (G100 b): the start button shows it instead of pretending.
    private(set) var watchLink = Lift.WatchLink.notActivated
    /// The last time anything arrived from the Watch app (G107): a message, a session or discard, a mirrored session or
    /// its live state. Evidence of a working link that `isWatchAppInstalled` can't give on the free team.
    private(set) var lastHeardFromWatch: Date?
    @ObservationIgnored private let network = NWPathMonitor()
    /// The last path update said no network (G98 a).
    @ObservationIgnored private var offline = false

    /// The Watch's `sendMessage(["swapRequest": id, "sessionId", "slot", "exercise", "setNumber", "sets"])`.
    struct SwapRequest: Identifiable {
        let id: String // echoed in the answer; the Watch drops a stale one
        let slot: String
        let exercise: String
        let setNumber: Int?
        let sets: Int?
    }

    var pendingCount: Int { outbox.pending.count }
    /// The latest session the Watch finished with sets (sent, pending or refused), for the rotation suggestion (G40, N6).
    var lastFinished: Session? { Session.lastFinished(outbox.items.values.map(\.session)) }

    override init() {
        super.init()
        #if DEBUG
        if UITestFixture.isOn { // UI tests: fixed data in memory; no network, no Watch, nothing written
            token = "ui-test"
            outbox = UITestFixture.outbox
            let data = UITestFixture.snapshot
            plan = try? Plan.decoder.decode(SnapshotEnvelope.self, from: data).payload.workout
            entreno = try? Plan.decoder.decode(EntrenoSnapshot.self, from: data)
            watchLink = .appMissing
            return
        }
        #endif
        outbox = Self.loadOutbox()
        loadCachedSnapshot() // offline cold launch (gym basement): the last good plan, its age on screen (EN-11)
        // G98 (a), i10: when the network comes back, a refresh that failed offline runs again by itself (the "Sin
        // conexión" line clears, waiting sessions go out) without a pull-to-refresh. @Sendable: called on its queue.
        network.pathUpdateHandler = { @Sendable [weak self] path in
            let up = path.status == .satisfied
            Task { @MainActor in
                guard let self else { return }
                let back = up && (self.offline || self.lastRefresh == .offline)
                self.offline = !up
                if back { await self.refresh() }
            }
        }
        network.start(queue: DispatchQueue(label: "athleteos.network"))
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    // MARK: Worker

    private func request(_ path: String, method: String = "GET", body: Data? = nil) -> URLRequest {
        Server.request(path, method: method, body: body, token: token)
    }

    func login(email: String, password: String) async {
        struct Reply: Decodable { let token: String }
        do {
            let body = try JSONEncoder().encode(["email": email, "password": password])
            let (data, resp) = try await URLSession.shared.data(for: request("api/auth/login", method: "POST", body: body))
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
                status = "Login fallido (\((resp as? HTTPURLResponse)?.statusCode ?? 0))"
                return
            }
            let t = try JSONDecoder().decode(Reply.self, from: data).token
            Keychain.save(t)
            token = t
            status = ""
            await refresh()
        } catch {
            status = "Login fallido: \(error.localizedDescription)"
        }
    }

    func logout() {
        Keychain.delete()
        token = nil
        // The cached plan holds private notes: gone with the account. The outbox stays (sessions are never dropped).
        try? FileManager.default.removeItem(at: Self.snapshotURL)
        plan = nil
        entreno = nil
        sendContextToWatch() // the Watch drops its copy of the token too (G103)
    }

    func refresh() async {
        #if DEBUG
        if UITestFixture.isOn { return }
        #endif
        updateWatchLink()
        guard token != nil else { return }
        await fetchSnapshot()
        await flush()
    }

    private func fetchSnapshot() async {
        let data: Data, code: Int?
        do {
            let (d, resp) = try await URLSession.shared.data(for: request("api/snapshot/latest"))
            (data, code) = (d, (resp as? HTTPURLResponse)?.statusCode)
        } catch {
            lastRefresh = .offline
            status = "Sin conexión: \(error.localizedDescription)"
            return
        }
        lastRefresh = code == 200 || code == 204 ? .ok : .offline // 200: `apply` says whether the body was usable
        switch code {
        case 200:
            lastSync = .now
            UserDefaults.standard.set(lastSync, forKey: "lastSync")
            guard apply(data) else { return } // kept the cached plan; `status` says why
            try? FileManager.default.createDirectory(at: .applicationSupportDirectory, withIntermediateDirectories: true)
            // Holds private guide notes: readable after the first unlock only (background relays still work).
            try? data.write(to: Self.snapshotURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
            sendContextToWatch()
        case 204: status = "Aún no hay snapshot publicado"
        case 401: logout()
        case let code: status = "Snapshot: error \(code ?? 0)"
        }
    }

    /// Reads a snapshot body into `plan` (the Watch document) and `entreno` (the phone's screens), separately: an
    /// Entreno field the phone can't read never stops the Watch's plan (EN-29). Refuses a newer schema major and an
    /// unreadable plan, keeping what it had. True when the body is good enough to keep as the last good snapshot.
    @discardableResult
    private func apply(_ data: Data) -> Bool {
        // The version first: a newer major may not decode as this build's types at all (re-check N3).
        if let version = EntrenoSnapshot.schemaVersion(of: data), !EntrenoSnapshot.isSupported(version) {
            lastRefresh = .unsupported
            status = "El snapshot usa un formato más nuevo que esta versión. Actualiza la app."
            return false
        }
        let envelope: SnapshotEnvelope
        do {
            envelope = try Plan.decoder.decode(SnapshotEnvelope.self, from: data)
        } catch {
            lastRefresh = .unreadable
            status = "El snapshot no se pudo leer: \(error.localizedDescription)"
            return false
        }
        guard let workout = envelope.payload.workout else { // keep the last good plan rather than none
            lastRefresh = .unreadable
            status = "El snapshot no trae entreno"
            return false
        }
        plan = workout
        UserDefaults.standard.set(envelope.publishedAt, forKey: "publishedAt")
        do {
            entreno = try Plan.decoder.decode(EntrenoSnapshot.self, from: data)
            status = ""
        } catch {
            entreno = nil
            status = "El entreno publicado no se pudo leer: \(error.localizedDescription)"
        }
        return true
    }

    private static var snapshotURL: URL { URL.applicationSupportDirectory.appending(path: "snapshot.json") }

    private func loadCachedSnapshot() {
        guard let data = try? Data(contentsOf: Self.snapshotURL) else { return }
        apply(data)
        lastRefresh = .ok // a bad copy on disk isn't a refresh: Ajustes shows why, the first refresh replaces it
        if !status.isEmpty { status = "Copia guardada: \(status)" }
    }

    /// PUTs every session whose latest rev the Worker hasn't accepted, acking each accepted rev back
    /// to the Watch. A `400` (the Worker refused the document) parks that session as "Rechazada" and the
    /// flush goes on with the rest; any other failure stops and keeps everything for the next try.
    /// Re-reads `pending` each turn so a rev that arrives mid-flush goes out in the same run.
    func flush() async {
        #if DEBUG
        if UITestFixture.isOn { return } // its fake token would get a 401 → logout() → the real Keychain token gone
        #endif
        guard token != nil, !flushing else { return }
        flushing = true
        defer { flushing = false }
        while let session = outbox.pending.first {
            do {
                let body = try Session.encoder.encode(session)
                let (data, resp) = try await URLSession.shared.data(for: request("api/workout/session", method: "PUT", body: body))
                let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                switch UploadReply(status: code) {
                case .accepted:
                    outbox.markSent(id: session.id, rev: session.rev)
                    saveOutbox()
                    ack(session.id)
                case .refused: // bad document: retrying won't help; park it, keep it, go on
                    let why = String(decoding: data.prefix(300), as: UTF8.self)
                    outbox.reject(id: session.id, rev: session.rev, error: "Error 400\(why.isEmpty ? "" : ": \(why)")")
                    saveOutbox()
                    ack(session.id) // the Watch shows "Rechazada"
                case .signedOut, .retry:
                    if code == 401 { logout() }
                    status = "Envío de sesión: error \(code); se reintentará"
                    return
                }
            } catch {
                status = "Envío de sesión: \(error.localizedDescription); se reintentará"
                return
            }
        }
    }

    // MARK: Watch

    func updateWatchLink() {
        #if DEBUG
        if UITestFixture.isOn { return } // the fixture's "app not installed" stays
        #endif
        let wc = WCSession.default
        let on = WCSession.isSupported() && wc.activationState == .activated
        watchLink = Lift.WatchLink(activated: on, paired: on && wc.isPaired, appInstalled: on && wc.isWatchAppInstalled,
                                   reachable: on && wc.isReachable,
                                   heardAgo: lastHeardFromWatch.map { Date.now.timeIntervalSince($0) })
    }

    /// Something arrived from the Watch app: the link works, whatever `isWatchAppInstalled` says (G107).
    func heardFromWatch(at date: Date = .now) {
        if lastHeardFromWatch.map({ $0 >= date }) == true { return }
        lastHeardFromWatch = date
        updateWatchLink()
    }

    /// Sends the plan, when this phone last checked the server for it + its publish date (G51: the Watch's "Plan
    /// comprobado" line; they travel only beside the plan, SY-11) and the theme (G43) as one application context. The
    /// context replaces the whole dictionary, so it starts from the last one sent: a theme change before this launch's
    /// snapshot keeps the Watch's plan.
    /// `resend`: stamps the context so WatchConnectivity delivers it even when nothing else changed ("Reiniciar
    /// conexión"); the Watch ignores the stamp.
    func sendContextToWatch(resend: Bool = false) {
        guard WCSession.default.activationState == .activated else { return }
        var context = WCSession.default.applicationContext
        if resend { context["resentAt"] = Date() }
        context["theme"] = UserDefaults.standard.string(forKey: "theme") ?? AppTheme.magenta.rawValue
        if let lastSync { context["syncedAt"] = lastSync }
        context["publishedAt"] = UserDefaults.standard.string(forKey: "publishedAt")
        // G103: the Watch uploads its finished sessions and reads the plan itself; "" = signed out, it deletes its copy.
        // lean: the full owner token over WatchConnectivity (encrypted device to device); a revocable device token
        // before a second user.
        context["ownerToken"] = token ?? ""
        context["gyms"] = try? JSONEncoder().encode(gyms)
        do {
            if let plan { context["plan"] = try Plan.encoder.encode(plan) }
            try WCSession.default.updateApplicationContext(context)
        } catch {
            status = "Reloj: \(error.localizedDescription)"
        }
    }

    /// Tells the Watch the highest rev of this session the Worker accepted ("Enviado ✓"), or that it refused
    /// the latest rev ("Rechazada", audit #8; its own key, so an older Watch build ignores it).
    private func ack(_ id: String) {
        guard WCSession.default.activationState == .activated, let item = outbox.items[id] else { return }
        if item.rejected != nil {
            WCSession.default.transferUserInfo(["rejected": id, "rev": item.session.rev])
        } else if let rev = outbox.ackRev(id: id) {
            WCSession.default.transferUserInfo(["ack": id, "rev": rev])
        }
    }

    /// "Descartar" on a "Rechazadas" row (G51 / SY-09): the athlete read why and lets it go. The phone forgets it and
    /// the Watch stops flagging that rev (it keeps the file). A newer rev of it would be sent and judged again.
    func dismissRejected(_ id: String) {
        guard let rev = outbox.dismiss(id: id) else { return } // a newer rev came in meanwhile: it's pending, keep it
        saveOutbox()
        if WCSession.default.activationState == .activated { WCSession.default.transferUserInfo(["dismissed": id, "rev": rev]) }
    }

    private func receive(_ session: Session, final: Bool) {
        if outbox.receive(session, final: final) {
            // G91: a late Watch rev of a deleted session — the emptied rev (re-numbered above it) goes to the Watch again.
            if let item = outbox.items[session.id], item.deleted != nil { publish(item.session) } else { saveOutbox() }
        }
        ack(session.id) // a resend's ack may have been lost; a note merged into a phone edit still gets one (ED-02)
        flushInBackground()
    }

    /// "Guardar" on the 24 h edit (G70): one new rev into the outbox → the Worker, then the Watch adopts it (stores it,
    /// never re-sends it). False when nothing changed or the session isn't a finished one we hold.
    @discardableResult
    func saveEdit(_ edited: Session) -> Bool {
        guard let doc = outbox.save(edit: edited) else { return false }
        publish(doc)
        return true
    }

    /// A rev the phone wrote (an edit, a delete, a restore): saved, uploaded, and adopted by the Watch (stored there,
    /// never re-sent).
    private func publish(_ doc: Session) {
        saveOutbox()
        flushInBackground()
        if WCSession.default.activationState == .activated, let data = try? Session.encoder.encode(doc) {
            WCSession.default.transferUserInfo(["adopt": data])
        }
    }

    /// Every change to the gym list: kept on this phone and sent to the Watch.
    func updateGyms(_ change: (inout Gyms) -> Void) {
        change(&gyms)
        UserDefaults.standard.set(try? JSONEncoder().encode(gyms), forKey: "gyms")
        sendContextToWatch()
    }

    func canDelete(_ id: String, now: Date = .now) -> Bool { outbox.canDelete(id: id, now: now) }

    /// "Borrar sesión" (G91): an emptied rev goes to the server (the pull drops its rows) and to the Watch ("Última"
    /// skips it); the original stays here for "Deshacer" / "Recuperar".
    func deleteSession(_ id: String) {
        guard let doc = outbox.delete(id: id, now: .now) else { return }
        publish(doc)
        justDeleted = id
        // G101 b: the timer lives here, not on the banner, so it runs the same whichever screen is showing.
        #if DEBUG
        let seconds = UITestFixture.undoSeconds
        #else
        let seconds = 8.0
        #endif
        Task {
            try? await Task.sleep(for: .seconds(seconds))
            if justDeleted == id { justDeleted = nil }
        }
    }

    func restoreSession(_ id: String) {
        guard let doc = outbox.restore(id: id) else { return }
        publish(doc)
        if justDeleted == id { justDeleted = nil }
    }

    /// "Reiniciar conexión" (G98 c), instead of quitting the app (Apple: never exit()): re-activates WatchConnectivity,
    /// resends the plan, re-acks recent sessions so the Watch's sync state is current, then refreshes (snapshot +
    /// flush). Returns the line to show. It can't fix iOS saying the Watch app isn't installed (G44): only reinstalling
    /// both apps together does.
    func restartConnection() async -> String {
        let wc = WCSession.default
        wc.delegate = self
        wc.activate()
        for _ in 0..<10 where wc.activationState != .activated { try? await Task.sleep(for: .milliseconds(500)) }
        sendContextToWatch(resend: true)
        // lean: the last 14 days only; older sessions are long confirmed on the Watch.
        for item in outbox.items.values where Date.now.timeIntervalSince(item.session.startedAt) < 14 * 86_400 {
            ack(item.session.id)
        }
        await refresh() // also re-reads the Watch link
        if wc.activationState != .activated { return String(localized: "El reloj no se ha conectado. Reinicia el iPhone y prueba otra vez.") }
        if watchLink == .appMissing { // G107: not just the flag; recent evidence from the Watch counts as seen
            return String(localized: "El iPhone sigue sin ver la app del reloj. Reinstala las dos apps juntas desde el Mac, sin borrarlas antes.")
        }
        return status.isEmpty ? String(localized: "Conexión reiniciada ✓") : status
    }

    func canEdit(_ id: String, now: Date = .now) -> Bool { outbox.canEdit(id: id, now: now) }

    /// The athlete picked the substitute for the Watch's "Otro" (G69). Cancelar sends nothing: the Watch drops it.
    func answerSwap(_ choice: Plan.Choice) {
        guard let request = swapRequest else { return }
        swapRequest = nil
        WCSession.default.transferUserInfo(["swapReply": request.id, "templateId": choice.templateId, "name": choice.name])
    }

    /// Uploads whatever is pending — also a held rev whose first PUT failed (audit #1: a Watch re-send or WC
    /// activation retries it, not only a new rev or opening the app).
    private func flushInBackground() {
        guard !outbox.pending.isEmpty else { return }
        // The Watch wakes this app in the background; ask iOS for time to finish the upload.
        let app = UIApplication.shared
        var task = UIBackgroundTaskIdentifier.invalid
        task = app.beginBackgroundTask(withName: "flush") { app.endBackgroundTask(task) }
        Task {
            await flush()
            app.endBackgroundTask(task)
        }
    }

    // MARK: Outbox file

    private static var outboxURL: URL { URL.applicationSupportDirectory.appending(path: "outbox.json") }

    private static func loadOutbox() -> Outbox {
        guard let data = try? Data(contentsOf: outboxURL) else { return Outbox() }
        if let box = try? Session.decoder.decode(Outbox.self, from: data) { return box }
        // Never overwrite a file we can't read: set it aside for a human to recover.
        try? FileManager.default.moveItem(at: outboxURL, to: outboxURL.deletingLastPathComponent()
            .appending(path: "outbox-unreadable-\(Int(Date.now.timeIntervalSince1970)).json"))
        return Outbox()
    }

    private func saveOutbox() {
        #if DEBUG
        if UITestFixture.isOn { return } // never overwrite the real outbox on the owner's iPhone
        #endif
        do {
            try FileManager.default.createDirectory(at: .applicationSupportDirectory, withIntermediateDirectories: true)
            try Session.encoder.encode(outbox).write(to: Self.outboxURL, options: .atomic)
        } catch {
            status = "No se pudo guardar la bandeja: \(error.localizedDescription)"
        }
    }
}

extension PhoneModel: WCSessionDelegate {
    nonisolated func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {
        Task { @MainActor in
            self.updateWatchLink()
            self.sendContextToWatch()
            self.flushInBackground()
        }
    }

    nonisolated func sessionWatchStateDidChange(_ session: WCSession) {
        Task { @MainActor in self.updateWatchLink() }
    }

    nonisolated func sessionReachabilityDidChange(_ session: WCSession) {
        Task { @MainActor in self.updateWatchLink() }
    }

    /// "Sincronizar ahora" on the Watch (G51): refresh (snapshot + flush) on the main actor like every other delegate
    /// call — `flushing` and the outbox must not race a background flush — then reply what the Watch can't see.
    nonisolated func session(_ session: WCSession, didReceiveMessage message: [String: Any],
                             replyHandler: @escaping ([String: Any]) -> Void) {
        Task { @MainActor in self.heardFromWatch() }
        if let id = message["swapRequest"] as? String, let slot = message["slot"] as? String { // G69: the reply = "heard"
            let request = SwapRequest(id: id, slot: slot, exercise: message["exercise"] as? String ?? "",
                                      setNumber: message["setNumber"] as? Int, sets: message["sets"] as? Int)
            Task { @MainActor in self.swapRequest = request }
            return replyHandler([:])
        }
        guard message["sync"] as? Bool == true else { return replyHandler([:]) }
        nonisolated(unsafe) let replyHandler = replyHandler // WatchConnectivity allows replying from any thread
        Task { @MainActor in
            let app = UIApplication.shared // the message may have woken this app in the background
            var task = UIBackgroundTaskIdentifier.invalid
            task = app.beginBackgroundTask(withName: "sync") { app.endBackgroundTask(task) }
            await self.refresh()
            replyHandler(["signedIn": self.token != nil, "watchAppInstalled": WCSession.default.isWatchAppInstalled,
                          "error": self.token == nil ? "" : self.status])
            app.endBackgroundTask(task)
        }
    }

    nonisolated func sessionDidBecomeInactive(_ session: WCSession) {}

    nonisolated func sessionDidDeactivate(_ session: WCSession) {
        WCSession.default.activate() // Watch switched; reconnect to the new one
    }

    nonisolated func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        Task { @MainActor in self.heardFromWatch() }
        if userInfo["discard"] as? Bool == true, let id = userInfo["id"] as? String {
            Task { @MainActor in
                self.outbox.discard(id: id)
                self.saveOutbox()
            }
            return
        }
        guard let data = userInfo["session"] as? Data,
              let doc = try? Session.decoder.decode(Session.self, from: data) else { return }
        let final = userInfo["final"] as? Bool == true // G70: the Watch won't write this session again
        Task { @MainActor in self.receive(doc, final: final) }
    }
}
