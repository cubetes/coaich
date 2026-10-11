import Foundation
import HealthKit
import WatchConnectivity
import WatchKit
import AthleteCore
#if DEBUG
import os

/// G25 device check: "detent" (the model took a notch) → "box" (the value box drew it), with timestamps.
/// Console.app → the Watch → Action ▸ Include Debug Messages, search `subsystem:athleteos category:crown`.
let crownLog = Logger(subsystem: "athleteos", category: "crown")
#endif

/// The Watch's session engine: plan from the phone, the session document (saved to disk on every
/// change and sent whole to the phone), and the HealthKit strength workout with live heart rate.
@Observable
final class WatchModel: NSObject {
    /// The plan in force; one that arrives mid-session waits until the session ends (RT-18).
    var inbox = PlanInbox()
    var plan: Plan? { inbox.plan }
    var session: Session?
    var heartRate: Double?
    /// When `heartRate` was measured: older than 15 s it shows as "—" (G79, red team MT-05).
    var heartRateAt: Date?
    /// The heart rate to show at `now` (nil = "—", no zone).
    func liveHeartRate(at now: Date) -> Double? { HRZones.live(heartRate, at: heartRateAt, now: now) }
    /// Heart-rate readings of the running session (Métricas graph, zones, recovery). Memory, refilled from HealthKit
    /// after a relaunch (`recoverWorkout`, G79).
    var hrSamples: [HRSample] = []
    /// The Métricas Crown view on screen (0 Métricas · 1 Zonas · 2 Pulso, G79/G99); wrist-down sets it back to 0.
    var metricsView = 0
    /// Active kcal so far, from the HealthKit builder's statistics; nil until HealthKit reports it.
    var activeKcal: Double?
    /// Age from HealthKit's date of birth, for the zone split (`HRZones`); nil → `HRZones.fallbackAge`.
    var age: Int?
    var maxHR: Double { HRZones.maxHR(age: age ?? HRZones.fallbackAge) }
    /// Rest-timer windows of the running session (Métricas recovery, work vs rest). Kept in the session file (G79).
    var rests: [DateInterval] {
        get { session?.rests ?? [] }
        set { session?.rests = newValue.isEmpty ? nil : newValue }
    }
    /// Start countdown (L9): the routine about to start and when the countdown began; `goAt` is set while
    /// "¡Vamos!" shows (the session already runs underneath).
    var countdown: (routineKey: String, began: Date)?
    var goAt: Date?
    private var countdownTask: Task<Void, Never>?
    private var hkPrep: Task<Void, Never>?
    var status = ""
    /// The slot the Set page shows. Any slot can be picked on Overview or with "Cambiar"; after a slot's
    /// last set the Watch proposes the first pending slot in routine order on the rest page (L4).
    var currentSlot: String?
    /// The current slot was proposed by the Watch, not picked: its first set needs a touch on Hecho
    /// (no Double Tap), so a set done elsewhere can't land in it blind (RT-04).
    var autoPicked = false
    /// Sets added with "+1 serie", per slot. Kept in the session file, so a relaunch keeps them (G79, red team MT-02).
    var addedSets: [String: Int] {
        get { session?.addedSets ?? [:] }
        set { session?.addedSets = newValue.isEmpty ? nil : newValue }
    }
    /// Working sets done / planned: the one count of Métricas, Resumen, the summary and the lock-screen bar (G79).
    var progress: Plan.Progress {
        guard let rk = routineKey, let plan else { return .init(done: session?.exercises.flatMap(\.sets).working.count ?? 0, planned: 0) }
        return plan.progress(routineKey: rk, session: session, added: addedSets)
    }
    /// The first heart-rate reading came more than 2 min after the start (a relaunch HealthKit couldn't refill): the
    /// graph and averages say "desde hh:mm" instead of claiming the whole session (G79, red team MT-04).
    var hrSince: Date? {
        guard let start = session?.startedAt, let first = hrSamples.first?.t, first.timeIntervalSince(start) > 120 else { return nil }
        return first
    }

    // Live set draft (kept here, not in the view, so it survives wrist-down, page swipes and sheets).
    var draft = Draft()
    /// nil = no kg yet (a substitute's first set, G69): the box is empty and Hecho is refused until one is set.
    var kg: Double? { get { draft.kg } set { draft.kg = newValue } }
    var reps: Int { get { draft.reps } set { draft.reps = newValue } }
    var type: Session.SetType { get { draft.type } set { draft.type = newValue } }
    /// The last kg typed on the keypad: the barbell "No cargable" hint stays quiet for it (G14).
    var typedKg: Double?
    /// The number the Crown edits; remembered across sets (must-fix 4).
    var field = Field.kg
    /// Back/forward between the slot's sets (L8). Back to the live set on wrist-down / background only (G21).
    /// Also whether the Crown is armed (a tap on a value box; audit #3).
    var nav = SetNavigator()
    /// A set un-logged in the last 4 s, for "Deshacer" — only on its own exercise (N8).
    var undo = PendingUndo()
    /// Slots whose warm-up guide was closed with "Empezar series" (G67); "↶ Calentamiento" reopens it. Memory only:
    /// after a relaunch the guide shows again on a slot with no working set, which is harmless.
    var warmupClosed: Set<String> = []
    /// "Otro (en el iPhone)" waiting for the phone's pick (G69); `swapSilent` once the phone said nothing for 20 s.
    var swapRequest: SwapRequest?
    var swapSilent = false
    struct SwapRequest: Equatable {
        let id: String
        let session: String
        let slot: String
        let at: Date
        // lean: a pick older than this is dropped (the athlete moved on); a real timeout UI only if it bites.
        static let expiry: TimeInterval = 5 * 60
    }
    /// A Crown edit to a logged set, saved once the Crown settles (G25). Not observed: no view draws it.
    @ObservationIgnored private var pendingSave = PendingSave()
    private var undoTask: Task<Void, Never>?

    /// Rest countdown end; non-nil while the rest timer owns the Set page.
    var restEnd: Date?
    /// When the current rest began, and its planned length (the rest bar).
    var restStart: Date?
    var restBase: TimeInterval = 90
    /// Seconds added/removed on this rest ("+30 s" chip).
    var nudge = 0
    /// The slot whose set started the rest (RIR chips edit its last set).
    var restSlot: String?
    /// Touch/Crown lockout after Set ↔ Rest flips and page jumps (RT-01/02/09); `lockTick` re-renders
    /// the views when the window closes.
    var lockout = Lockout()
    var lockTick = 0
    /// A rest ended with nothing left to do: the session shows Resumen scrolled to Terminar (G22); Resumen
    /// clears it once it has scrolled.
    var showFinish = false
    /// "¿Has terminado?" after 20 idle minutes; auto-end at 45 (Q21).
    var askFinish = false
    private var idleSnooze = Date.distantPast
    /// Revs the phone confirmed reached the Worker.
    var acks = WatchModel.loadAcks()
    /// Every session file on the Watch (kept in step by `save` / `discard`) and how many files won't decode: what the
    /// sync button counts (G51). An unreadable file is a problem, never "Al día" (SY-02).
    var stored: [Session] = []
    var unreadable = 0
    /// Most recent finished session with sets, for the "Última" line and the rotation suggestion (G40; N6).
    var lastSession: Session? { Session.lastFinished(stored) }
    var syncStatus: SyncStatus { SyncStatus.of(stored, unreadable: unreadable, acks: acks) }
    /// When the phone last checked the server for the plan, and the plan's publish date (application context
    /// `syncedAt` / `publishedAt`, trusted only beside a plan in the same dictionary, SY-11). Never a session time (SY-01).
    var planCheckedAt: Date?
    var planPublishedAt: String?
    /// "Sincronizar ahora" / auto-sync (G51): a request is out (the button is disabled); the athlete is watching it
    /// (the glyph spins, the sheet shows the result); the last result, cleared when the sheet closes.
    var syncing = false
    var syncManual = false
    var syncResult: SyncResult?
    @ObservationIgnored private var lastSyncAttempt: Date?
    /// The phone's gym list (G92, G111), kept from its application context.
    var gyms = (UserDefaults.standard.data(forKey: "gyms")).flatMap { try? JSONDecoder().decode(Gyms.self, from: $0) } ?? Gyms()
    /// The gym picked on the routine list for the next session (switch on only); nil = the default.
    var pickedGym: String?
    /// The gym the next session gets, as the routine list shows it.
    var nextGym: String? { gyms.forNewSession(picked: pickedGym, last: lastSession?.gymId) }
    /// The Watch's own upload to the Worker is running (G103): one at a time.
    @ObservationIgnored private var uploading = false
    @ObservationIgnored private var syncSeq = 0
    /// The session just finished: its summary (G41), then "¿Cómo ha ido?" (G42). Memory only; the session is
    /// already saved and sent — the note goes out as a new rev.
    var finished: (session: Session, summary: Stats.Summary)?
    /// Neón verde theme (G43), from the phone's application context. Applied only outside a session (a re-render
    /// mid-session would reset the page), like a plan that arrives mid-session (RT-18).
    var neon = false

    private var restTask: Task<Void, Never>?
    private var idleTask: Task<Void, Never>?

    /// Start from iPhone: the WatchConnectivity request and the app launch, matched (G15).
    @ObservationIgnored private var phoneStart = PhoneStart()
    /// The live state last sent over the mirrored workout (G15); only a change is sent.
    @ObservationIgnored private var liveSent: LiveState?
    @ObservationIgnored private var liveInFlight: LiveState?
    /// Numbers each send, so only the newest send's completion records `liveSent` or retries (LA-01).
    @ObservationIgnored private var liveSeq = 0
    @ObservationIgnored private var livePending = false
    /// Mirroring is retried once after the phone drops off, never after the workout ends.
    @ObservationIgnored private var mirrorRetried = false

    private let store = HKHealthStore()
    private var hkSession: HKWorkoutSession?
    private var builder: HKLiveWorkoutBuilder?

    /// Xcode previews (`Previews.swift`): demo plan, nothing written, sent or measured.
    private var isPreview = false

    override convenience init() { self.init(preview: false) }

    init(preview: Bool) {
        super.init()
        #if DEBUG
        if preview {
            isPreview = true
            inbox = PlanInbox(plan: Demo.plan)
            return
        }
        if Demo.isOn { // sample plan, no phone, fresh sessions folder
            try? FileManager.default.removeItem(at: Self.sessionsDir)
            inbox = PlanInbox(plan: Demo.noPlan ? nil : Demo.plan)
            (stored, unreadable, acks) = Demo.syncSeed()
            planCheckedAt = Demo.planCheckedAt
            planPublishedAt = Demo.publishedAt
            UserDefaults.standard.set(Demo.neon ? "neon" : "magenta", forKey: "theme")
            applyTheme()
            return
        }
        #endif
        applyTheme()
        (stored, unreadable) = Self.allSessions()
        session = stored.filter { $0.endedAt == nil }.max { $0.startedAt < $1.startedAt }
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
        Task { await syncDirect() } // G103: no need to wait for the phone
        if session != nil {
            Task {
                await recoverWorkout()
                watchIdle() // a session left open overnight finishes at its last set (RT-17)
            }
        }
    }

    /// The routine key of the running session (sessions carry only the title, per the contract).
    var routineKey: String? {
        guard let session, let plan else { return nil }
        return plan.routines.first { $0.value.title == session.routineTitle }?.key
    }

    // MARK: Session

    /// Routine picked: full-screen 3 → 2 → 1 → "¡Vamos!" (L9). HealthKit prepares meanwhile, so heart rate
    /// is live by set 1. A click each second, `.start` at go. Nothing is logged during the countdown.
    func beginCountdown(routineKey: String) {
        guard countdown == nil, session == nil, plan?.routines[routineKey] != nil else { return }
        phoneStart = PhoneStart() // a phone request arriving late must not start a second routine
        finished = nil // a start from the iPhone closes the last summary: it must not come back after a discard
        let began = Date.now
        countdown = (routineKey, began)
        publishLive()
        hkPrep = Task { await prepareWorkout() }
        countdownTask = Task {
            for n in 0..<Countdown.seconds {
                WKInterfaceDevice.current().play(.click)
                try? await Task.sleep(for: .seconds(max(began.addingTimeInterval(Double(n + 1)).timeIntervalSinceNow, 0)))
                if Task.isCancelled { return }
            }
            await go()
        }
    }

    /// Tap or Double Tap on the countdown: start now.
    func skipCountdown() {
        countdownTask?.cancel()
        Task { await go() }
    }

    /// "¡Vamos!": the session starts now (`started_at` = this moment) and the prepared workout begins.
    private func go() async {
        guard let c = countdown, goAt == nil, session == nil, let routine = plan?.routines[c.routineKey] else { return }
        var now = Date.now
        #if DEBUG
        if Demo.late { now = now.addingTimeInterval(-89 * 60 - 7) }
        #endif
        goAt = .now
        session = Session(routineTitle: routine.title, startedAt: now)
        session?.gymId = nextGym // G92: on every rev; nil until the phone has a gym list
        pickedGym = nil
        idleSnooze = .now
        hrSamples = []
        heartRateAt = nil
        metricsView = 0
        activeKcal = nil
        nav.reset()
        warmupClosed = []
        currentSlot = plan?.firstPendingSlot(routineKey: c.routineKey, session: session)
        autoPicked = false
        syncDraft() // the first "Obj" the phone shows is this slot's, not the last session's draft (v0.4.1 M1)
        persistAndSend() // saved on the Watch; not sent until the first confirmed set
        WKInterfaceDevice.current().play(.start) // the stronger beat at go
        Task {
            try? await Task.sleep(for: .seconds(Countdown.goHold))
            countdown = nil
            goAt = nil
            flip() // a skip tap repeated as the Set page appears must not land on Hecho
        }
        await startPrepared(at: now)
        watchIdle()
    }

    var currentPlanSlot: Plan.Slot? { currentSlot.flatMap { plan?.slots[$0] } }
    /// What a slot does now: the plan's exercise or, after a swap, the substitute (G69).
    func inUse(_ key: String?) -> Plan.Slot.InUse? {
        guard let key, let slot = plan?.slots[key] else { return nil }
        return slot.inUse(session?.currentExercise(forSlot: key))
    }
    var currentInUse: Plan.Slot.InUse? { inUse(currentSlot) }
    /// The superset partner's name for the Set page's "🔗" line (G39, G55): short name first; the substitute after a swap.
    var supersetPartnerInUse: Plan.Slot.InUse? {
        guard let key = currentSlot, let rk = routineKey else { return nil }
        return inUse(plan?.supersetPartner(of: key, routineKey: rk))
    }
    var supersetPartner: String? { supersetPartnerInUse?.short }
    var confirmedInSlot: [Session.SetEntry] { currentSlot.flatMap { session?.sets(forSlot: $0) } ?? [] }
    /// What Hecho logs now (nil when the slot is done). kg never carries across a swap (G69, SB-01).
    var livePrefill: PlannedSet? {
        guard let key = currentSlot, let slot = plan?.slots[key] else { return nil }
        return slot.prefill(session: session, slot: key, added: addedSets[key] ?? 0)
    }
    /// Where the plates start and on how many sleeves (G68); nil = no plate line — a stack, dumbbells, a substitute
    /// (its equipment is unknown), or a snapshot without `start_kg` (red team PL-01, `Plan.plateLine`).
    var plates: (start: Double, sides: Int)? {
        guard let key = currentSlot, currentInUse?.substituted != true else { return nil }
        return plan?.plateLine(key)
    }
    /// The quiet "No cargable" hint and the 2,5 Crown: the plate line's start, else the 20 kg bar on a barbell slot
    /// of an older snapshot (as in v0.5.0); nil on a substitute.
    var loadStart: (start: Double, sides: Int)? {
        guard let slot = currentPlanSlot, currentInUse?.substituted != true else { return nil }
        return plates ?? slot.plateStart.map { ($0, 2) }
    }
    /// kg per Crown notch on the current exercise: 2,5 on plate-loaded slots, 1,25 else and on a substitute.
    private func stepKg(_ kg: Double, by d: Int) -> Double {
        let known = currentInUse?.substituted != true
        return Entry.step(kg: kg, by: d, equipment: known ? currentPlanSlot?.equipment : nil,
                          startKg: known ? loadStart?.start : nil)
    }

    /// Reloads the live draft when the set it belongs to changes (new set, slot, exercise after a swap, "+1 serie") or
    /// its carried-forward kg changes after a past set was corrected (N6).
    func syncDraft() {
        let key = currentSlot
        draft.sync(slot: key, template: key.flatMap { session?.currentExercise(forSlot: $0)?.exerciseTemplateId },
                   confirmed: confirmedInSlot.count, added: addedSets[key ?? ""] ?? 0, prefill: livePrefill)
    }

    // MARK: Warm-up guide (G67, option D: read-only)

    /// The ramp for the live first working kg (the draft, so a changed set 1 moves it). Empty on a substitute (its kg
    /// is unknown), once a working set is logged, or with no kg.
    var ramp: [PlannedSet] {
        guard let slot = currentPlanSlot, currentInUse?.substituted != true, confirmedInSlot.working.isEmpty else { return [] }
        return slot.warmupSets(workingKg: kg, startWeight: plates?.start)
    }

    /// The guide shows on the live set of a coach-marked slot until "Empezar series" (or a working set) closes it.
    var showsWarmup: Bool {
        guard let key = currentSlot, nav.isLive, undo.item == nil else { return false }
        return !warmupClosed.contains(key) && !ramp.isEmpty
    }

    /// The set menu's "↶ Calentamiento": the guide was closed and no working set is logged yet.
    var canReopenWarmup: Bool {
        guard let key = currentSlot, nav.isLive else { return false }
        return warmupClosed.contains(key) && !ramp.isEmpty
    }

    /// "Empezar series": Serie 1. Logs nothing and never touches the draft; the page under the finger changed, so the
    /// 1 s touch lockout. A touch also confirms a proposed exercise (N3).
    func startSets() {
        guard let key = currentSlot else { return }
        warmupClosed.insert(key)
        autoPicked = false
        flip()
    }

    func reopenWarmup() {
        guard let key = currentSlot else { return }
        warmupClosed.remove(key)
    }

    /// Set 1 after the ramp on a plate-loaded slot shows its plates unasked (panel must-fix 3).
    var platesAfterRamp: Bool {
        guard let key = currentSlot, plates != nil, nav.isLive else { return false }
        return warmupClosed.contains(key) && confirmedInSlot.working.isEmpty
    }

    // MARK: Substitution (G69)

    /// "⇄ Cambiar ejercicio": on the live set while the slot has sets to do.
    var canSwap: Bool {
        nav.isLive && livePrefill != nil && currentPlanSlot?.templateId != nil && session?.endedAt == nil
    }

    /// The coach's alternatives except the exercise in use.
    var swapChoices: [Plan.Slot.Alternative] {
        let now = currentSlot.flatMap { session?.currentExercise(forSlot: $0)?.exerciseTemplateId } ?? currentPlanSlot?.templateId
        return (currentPlanSlot?.alternatives ?? []).filter { $0.templateId != now }
    }

    /// Swaps the slot's next sets to `templateId` (ADR 0003). No confirm, no haptic (an edit, §5). Written to the
    /// Watch's file at once, same rev (SB-03): a crash before the next set must not lose it. kg starts empty (SB-01).
    func swap(to templateId: String, title: String) {
        guard let key = currentSlot, let planned = currentPlanSlot?.templateId,
              session?.substitute(slot: key, templateId: templateId, title: title, planned: planned) == true else { return }
        nav.reset()
        syncDraft()
        persistAndSend()
        flip() // back on the Set page under the finger
    }

    /// "↶ Volver a {short}": the pending sets go back to the plan's exercise, with its own kg (panel must-fix 13).
    func swapBack() {
        guard let slot = currentPlanSlot, let planned = slot.templateId else { return }
        swap(to: planned, title: slot.name)
    }

    /// "Otro (en el iPhone)": asks the phone to pick from the plan (`["swapRequest": id, "sessionId", "slot", …]`). The
    /// phone answers later with `["swapReply": id, "templateId", "name"]`; only the answer to this request, for this
    /// session and slot, within 5 min and while the athlete still waits, is applied (SB-08).
    func requestSwap() {
        guard let key = currentSlot, let s = session else { return }
        let r = SwapRequest(id: UUID().uuidString.lowercased(), session: s.id, slot: key, at: .now)
        swapRequest = r
        swapSilent = false
        swapHeard = false
        Task {
            try? await Task.sleep(for: .seconds(AutoSync.timeout))
            if swapRequest == r, !swapHeard { swapSilent = true } // "El iPhone no responde." (G51 words)
        }
        #if DEBUG
        if Demo.isOn { return } // no phone: the demo waits, then "no responde"
        #endif
        guard WCSession.default.activationState == .activated else { swapSilent = true; return }
        let info: [String: Any] = ["swapRequest": r.id, "sessionId": s.id, "slot": key,
                                   "exercise": currentInUse?.name ?? "", "setNumber": confirmedInSlot.working.count + 1,
                                   "sets": plan?.setCount(key, added: addedSets) ?? 0]
        WCSession.default.sendMessage(info, replyHandler: { @Sendable _ in
            Task { @MainActor in if self.swapRequest == r { self.swapHeard = true; self.swapSilent = false } }
        }, errorHandler: { @Sendable _ in
            Task { @MainActor in if self.swapRequest == r { self.swapSilent = true } }
        })
    }
    @ObservationIgnored private var swapHeard = false

    func cancelSwapRequest() { swapRequest = nil }

    /// The phone's pick for "Otro". Stale answers (another request, session or slot, cancelled, expired, the slot
    /// done meanwhile) are dropped.
    func swapReplied(id: String, templateId: String, name: String) {
        guard let r = swapRequest, r.id == id, session?.id == r.session, currentSlot == r.slot,
              Date.now.timeIntervalSince(r.at) < SwapRequest.expiry, canSwap else { return }
        swapRequest = nil
        swap(to: templateId, title: name)
    }

    /// Hecho on the live set (touch or Double Tap). Never acts on a logged set.
    func confirm() {
        guard nav.isLive, undo.item == nil, let key = currentSlot, let slot = plan?.slots[key],
              let templateId = slot.templateId, let planned = livePrefill, let kg, // no kg chosen yet: "Pon el peso" (G69)
              session?.canLog(slot: key) == nil, session?.endedAt == nil else { return } // contract caps (audit #8); never after Terminar
        session?.confirm(slot: key, templateId: templateId, title: slot.name,
                         planned: planned, weightKg: kg, reps: reps, type: type, at: .now)
        persistAndSend()
        WKInterfaceDevice.current().play(.success) // the only haptic for this action (must-fix 10)
        autoPicked = false
        guard let rk = routineKey, let session, let after = plan?.afterSet(key, routineKey: rk, session: session, added: addedSets)
        else { return startRest(slotKey: key, seconds: slot.restSeconds) }
        if let seconds = after.rest {
            startRest(slotKey: key, seconds: seconds)
        } else { // superset (G39): no rest, straight to the partner's next set; Hecho's `.success` is the only haptic
            nav.disarm()
            flip() // the Set page changed under the finger: 1 s touch lockout, so a second tap can't log the partner
        }
        // Next slot: the superset partner, or after a finished slot the first pending one, proposed on the rest page
        // with "Cambiar" (L4).
        if let next = after.next, next != key {
            currentSlot = next
            autoPicked = after.proposed
            undo.slotChanged(to: next)
        }
        syncDraft()
    }

    /// A slot picked by the athlete (Overview row or "Cambiar").
    func select(_ slotKey: String) {
        currentSlot = slotKey
        autoPicked = false
        undo.slotChanged(to: slotKey) // "Deshacer" never follows you to another exercise (N8)
        nav.reset()
        syncDraft()
        publishLive()
    }

    /// Slots with working sets still to do, in routine order, for "Cambiar".
    var pendingSlots: [String] {
        guard let rk = routineKey, let plan else { return [] }
        return plan.pendingSlots(routineKey: rk, session: session, added: addedSets)
    }

    /// Whether a session reached the server, as the Watch knows it (phone acks).
    func syncState(_ s: Session?) -> SyncState {
        guard let s, !s.isEmpty else { return .empty }
        return acks.isSent(s) ? .sent : acks.isRejected(s) ? .rejected : acks.isOnPhone(s) ? .onPhone : .pending
    }

    /// Why the slot can't take another set (contract caps, audit #8); nil = it can.
    func cap(_ slotKey: String) -> Session.Cap? { session?.canLog(slot: slotKey) }

    /// "+1 serie": one more set on the slot, pre-filled with its last confirmed set. Not past the 30-set cap.
    func addSet(slotKey: String) {
        guard cap(slotKey) == nil else { return }
        addedSets[slotKey, default: 0] += 1
        saveLocal() // in the file at once: a relaunch keeps it (G79)
        select(slotKey)
    }

    /// One Crown detent (`.low` sensitivity, one detent per unit) or a ±15 / VoiceOver adjust, which names its
    /// field. Ignored for 0,6 s after a flip. kg/reps change only once a value box was tapped (armed, audit #3);
    /// VoiceOver adjusts are deliberate and always apply.
    func step(_ d: Int, field named: Field? = nil) {
        guard d != 0, lockout.allowsCrown(at: .now) else { return }
        if restEnd != nil { return adjustRest(by: 15 * d) }
        guard nav.crownEdits || named != nil else { return }
        let f = named ?? field
        if let e = nav.editing, let key = currentSlot, let s = session?.sets(forSlot: key)[safe: e] {
            // In memory per notch; saved and sent once the Crown settles (G25). VoiceOver steps save at once.
            if session?.editSet(slot: key, index: e,
                                weightKg: f == .kg ? stepKg(s.weightKg, by: d) : s.weightKg,
                                reps: f == .reps ? Entry.step(reps: s.reps, by: d) : s.reps, type: s.type) == true {
                pendingSave.crownEdit()
                if named != nil { crownSettled() }
                syncDraft() // the live set picks up a corrected carried-forward kg (N6)
            }
        } else {
            if f == .kg {
                kg = stepKg(kg ?? 0, by: d) // the live draft: memory only until Hecho
            } else {
                reps = Entry.step(reps: reps, by: d)
            }
            if named != nil { publishLive() } // VoiceOver steps are deliberate; Crown notches wait for `crownSettled`
        }
        #if DEBUG
        crownLog.debug("detent \(d) → \(f == .kg ? "kg" : "reps")")
        #endif
    }

    /// The Crown came to rest (or the Watch leaves the front): a logged set's Crown edit is saved and sent now.
    func crownSettled() {
        if pendingSave.take() { persistAndSend() }
        publishLive() // a rest or live-draft target the Crown moved reaches the phone once, not per notch (G25)
    }

    /// 1-based planned-set number of the set on screen; nil for a warm-up, which counts for nothing (N7).
    var shownSetNumber: Int? {
        let done = confirmedInSlot
        if let e = nav.editing { return done[safe: e]?.type == .warmup ? nil : done.prefix(e).working.count + 1 }
        return type == .warmup ? nil : done.working.count + 1
    }

    /// The set on screen: the logged set being viewed, else nil (live draft).
    var viewedSet: Session.SetEntry? {
        guard let e = nav.editing, let key = currentSlot else { return nil }
        return session?.sets(forSlot: key)[safe: e]
    }

    /// Edits to a logged set save at once (L8 refinement: no separate "Guardar").
    func editLogged(kg: Double, reps: Int, type: Session.SetType) {
        guard let e = nav.editing, let key = currentSlot else { return }
        if session?.editSet(slot: key, index: e, weightKg: kg, reps: reps, type: type) == true {
            persistAndSend()
            syncDraft() // the live set picks up a corrected carried-forward kg (N6)
        }
    }

    /// A value box tapped. The first tap arms the Crown on that box (live or past set, audit #3 / N2); a tap on
    /// the armed box opens the keypad (returns true); a tap on the other box moves the Crown there. A touch also
    /// confirms a proposed exercise, so Double Tap works on it from now on (N3).
    func tapBox(_ f: Field) -> Bool {
        autoPicked = false
        if !nav.crownEdits { nav.arm(); field = f; return false }
        if field == f { return true }
        field = f
        return false
    }

    /// Keypad OK on the set on screen. Saved exactly as typed, any equipment (G14).
    func typed(_ value: Double, field f: Field) {
        if f == .kg { typedKg = value }
        if let s = viewedSet {
            editLogged(kg: f == .kg ? value : s.weightKg, reps: f == .reps ? Int(value) : s.reps, type: s.type)
        } else {
            if f == .kg { kg = value } else { reps = Int(value) }
            publishLive() // the new target reaches the phone once (G37)
        }
    }

    /// Set type from the long-press menu: on the set on screen (RT-10), never on another one.
    func setType(_ t: Session.SetType) {
        if let s = viewedSet { editLogged(kg: s.weightKg, reps: s.reps, type: t) } else { type = t; publishLive() }
    }

    /// "Registrada ✓" held 1 s (`Unlog.hold`; a tap does nothing, Double Tap never un-logs): the set goes back
    /// to pending, with a 4 s "Deshacer".
    func unlog() {
        guard let e = nav.editing, let key = currentSlot, let u = session?.unlog(slot: key, index: e) else { return }
        persistAndSend()
        nav.reset()
        undo.set(u)
        syncDraft()
        undoTask?.cancel()
        undoTask = Task {
            try? await Task.sleep(for: .seconds(4))
            if !Task.isCancelled { undo.clear() }
        }
    }

    func restoreUnlogged() {
        guard let u = undo.item else { return }
        undoTask?.cancel()
        session?.restore(u)
        undo.clear()
        persistAndSend()
        syncDraft()
    }

    func back() { nav.back(confirmed: confirmedInSlot.count) }

    func forward() { nav.forward(confirmed: confirmedInSlot.count) }

    /// Wrist down or the app leaving the foreground: back to the live set, so the next Double Tap logs it (N1).
    /// The only way back without a touch: G21 removed the 6 s timer.
    func backToLive() {
        crownSettled()
        nav.reset()
    }

    /// The set the rest page's RIR chips rate: the last set of the slot whose Hecho started the rest.
    var restRIRIndex: Int? { restSlot.flatMap { session?.sets(forSlot: $0).indices.last } }

    /// A RIR chip (rest page or a logged set, audit #5) — `.click` so a chosen RIR is felt (audit #2) — or the set
    /// menu's "Quitar RIR" (`nil`, no haptic). The only ways RIR changes.
    func setRIR(_ rir: Int?, slot: String, index: Int) {
        session?.setRIR(rir, slot: slot, index: index)
        persistAndSend()
        if rir != nil { WKInterfaceDevice.current().play(.click) }
    }

    /// Opens the touch/Crown lockout window (Set ↔ Rest flip, jump to the Set page).
    func flip() {
        lockout.flip(at: .now)
        Task {
            try? await Task.sleep(for: .seconds(Lockout.touch + 0.05))
            lockTick += 1
        }
    }

    // MARK: Rest timer

    /// Counts down on the main actor; the HealthKit workout keeps the app running with the wrist down.
    /// The last 5 s get stronger each second and 0 is a double strong buzz (G11; L6: drop to 3-2-1 if saved
    /// workouts show HR gaps). No haptic at the start: Hecho's `.success` already marks it (must-fix 10).
    private func startRest(slotKey: String, seconds: Int) {
        nav.disarm() // Hecho / rest start: the next set needs a new tap before the Crown edits it (audit #3)
        restSlot = slotKey
        restStart = .now
        restBase = TimeInterval(seconds)
        nudge = 0
        restEnd = .now.addingTimeInterval(TimeInterval(seconds))
        flip()
        restTask?.cancel()
        restTask = Task {
            var lastClick = Int.max
            while !Task.isCancelled, let end = restEnd {
                let left = end.timeIntervalSinceNow
                if left <= 0 {
                    WKInterfaceDevice.current().play(.notification) // double strong buzz: "go"
                    endRest()
                    try? await Task.sleep(for: .milliseconds(150))
                    WKInterfaceDevice.current().play(.notification)
                    return
                }
                let whole = Int(left.rounded(.up))
                if whole > 5 { lastClick = .max }
                else if whole < lastClick { WKInterfaceDevice.current().play(Self.restLadder[whole - 1]); lastClick = whole }
                try? await Task.sleep(for: .milliseconds(200))
            }
        }
    }

    /// Haptic at 1…5 s left: lighter the further from the end.
    private static let restLadder: [WKHapticType] = [.notification, .notification, .retry, .directionUp, .click]

    private func endRest() {
        if let restStart {
            rests.append(DateInterval(start: restStart, end: max(.now, restStart)))
            saveLocal()
        }
        restEnd = nil
        nav.disarm() // turns that continue past the rest's end never reach kg (audit #3)
        flip()
        publishLive()
        // The workout's last planned set and its rest are done: Resumen, at Terminar (G22).
        if pendingSlots.isEmpty, session?.isEmpty == false { showFinish = true }
    }

    /// ±15 s; turning down stops 5 s before the end (Saltar ends a rest), the chip counts what was applied.
    func adjustRest(by seconds: Int) {
        guard let end = restEnd else { return }
        let r = Rest.adjusted(end: end, by: TimeInterval(seconds), now: .now)
        restEnd = r.end
        nudge += Int(r.applied.rounded())
    }

    func skipRest() {
        guard restEnd != nil else { return }
        restTask?.cancel()
        endRest()
    }

    // MARK: Finish / discard / idle

    /// Finishes and saves. `at` is the end time (auto-end stamps the last set's time).
    func finish(at end: Date = .now) async {
        guard let current = session else { return }
        if current.finishDiscards { return await discard() } // never had a set: same as discarding
        session?.finish(at: end)
        let saved = persistAndSend()
        sendLive() // `ended` reaches the phone before the workout ends: ending it stops the mirroring
        if current.isEmpty { // every set un-logged (N9): the emptied doc is sent so the server drops the set; no Health workout
            discardWorkout()
        } else {
            await endWorkout(at: end, id: current.id)
            if saved { WKInterfaceDevice.current().play(.success) } // confirms the save, not the press
        }
        // G41: the summary holds the session as last saved — taken after the await, so an edit (RIR, un-log) made while
        // HealthKit ended the workout is in it and the note's rev (G42) never reuses a rev that went out without it.
        if let s = session, !s.isEmpty {
            finished = (s, Stats.summary(s, plan: plan, routineKey: routineKey, added: addedSets, samples: hrSamples, kcal: activeKcal))
        }
        endSessionState()
        autoSync(force: true) // G51: right after Terminar, so the phone flushes it now if it's in range
        Task { await uploadDirect() } // G103: and straight to the Worker, phone or not; never holds up the summary
    }

    private func endSessionState() {
        restTask?.cancel()
        idleTask?.cancel()
        restEnd = nil
        session = nil
        currentSlot = nil
        restSlot = nil
        warmupClosed = []
        swapRequest = nil
        undo.clear()
        askFinish = false
        nav.reset()
        inbox.sessionEnded() // a plan that arrived mid-session takes over now
        applyTheme() // and a theme picked on the phone meanwhile (G43)
    }

    /// "¿Cómo ha ido?" answered (G42): the note goes into the finished session as a new rev, saved and sent through
    /// the same path as every rev (the Worker ignores `note` until the companion PR stores it).
    func saveNote(_ text: String) {
        guard var f = finished else { return }
        if let adopted = stored.first(where: { $0.id == f.session.id }), adopted.rev > f.session.rev {
            f.session = adopted // the phone's newer copy (G70): the note goes on top of it, never over its edits
        }
        f.session.setNote(text)
        finished = f
        save(f.session)
    }

    /// Listo / Saltar after the summary: back to the routine list. The Watch is done writing this session: its last
    /// rev goes out with `final: true` (G70), so the phone may edit it.
    func closeSummary() {
        if let id = finished?.session.id { sendFinal(id) }
        finished = nil
        applyTheme() // a theme that arrived during the summary (G43)
    }

    /// Sends the stored session `id` with `final: true` (G70) — unless it is the phone's own rev (adopted).
    private func sendFinal(_ id: String) {
        guard let s = stored.first(where: { $0.id == id }), s.endedAt != nil, s.isSendable, !acks.isAdopted(s),
              let data = try? Session.encoder.encode(s) else { return }
        acks.markFinal(id: id, rev: s.rev) // the Watch's own upload stops at this rev (G103)
        UserDefaults.standard.set(try? JSONEncoder().encode(acks), forKey: "acks")
        send(data, id: id, final: true)
        Task { await uploadDirect() }
    }

    /// The phone's edited rev of a finished session (G70, `["adopt": data]`): stored, never re-sent, never for a
    /// session still running or a rev the Watch already has.
    func adopt(_ data: Data) {
        guard let s = try? Session.decoder.decode(Session.self, from: data), s.endedAt != nil, s.id != session?.id,
              let held = stored.first(where: { $0.id == s.id }), held.rev < s.rev, !isPreview else { return }
        guard save(s, send: false) else { return }
        acks.adopt(id: s.id, rev: s.rev)
        UserDefaults.standard.set(try? JSONEncoder().encode(acks), forKey: "acks")
    }

    /// Theme from the phone (G43): kept at once, shown once no session, countdown or summary is on screen (the redraw
    /// would drop the note being dictated).
    func receiveTheme(_ theme: String) {
        UserDefaults.standard.set(theme, forKey: "theme")
        if session == nil, countdown == nil, finished == nil { applyTheme() }
    }

    private func applyTheme() {
        neon = UserDefaults.standard.string(forKey: "theme") == "neon"
        Theme.neon = neon
    }

    /// "Seguir" on "¿Has terminado?": count idle time from now.
    func keepGoing() {
        idleSnooze = .now
        askFinish = false
    }

    private func watchIdle() {
        idleTask?.cancel()
        idleTask = Task {
            while !Task.isCancelled, let s = session {
                switch Idle.state(lastActivity: max(s.lastActivity, idleSnooze), now: .now) {
                case .active: break
                case .ask: askFinish = true
                case .autoEnd:
                    await finish(at: s.lastActivity)
                    return sendFinal(s.id) // nobody is there to close the summary (G70); a later note still merges on the phone
                }
                try? await Task.sleep(for: .seconds(30))
            }
        }
    }

    /// Throws the session away: no Apple Health workout, no file, never sent again.
    func discard() async {
        guard let id = session?.id else { return }
        try? FileManager.default.removeItem(at: Self.sessionsDir.appending(path: "\(id).json"))
        stored.removeAll { $0.id == id }
        if WCSession.default.activationState == .activated {
            for t in WCSession.default.outstandingUserInfoTransfers where t.userInfo["id"] as? String == id { t.cancel() }
            WCSession.default.transferUserInfo(["id": id, "discard": true])
        }
        sendLive(ended: true)
        discardWorkout()
        endSessionState()
    }

    /// Writes the running session's file without sending (Watch-only fields changed: `addedSets`, `rests`).
    private func saveLocal() {
        if let session, !isPreview { save(session, send: false) }
    }

    @discardableResult
    private func persistAndSend() -> Bool {
        guard let session, !isPreview else { return false }
        pendingSave.saved() // the whole session goes: a waiting Crown edit with it
        publishLive()
        return save(session)
    }

    /// Writes the session file and sends the document to the phone (an empty session in progress is never sent).
    @discardableResult
    private func save(_ session: Session, send sending: Bool = true) -> Bool {
        guard !isPreview else { return false }
        do {
            try FileManager.default.createDirectory(at: Self.sessionsDir, withIntermediateDirectories: true)
            try Session.fileEncoder.encode(session) // + addedSets and rests (G79); the wire copy never has them
                .write(to: Self.sessionsDir.appending(path: "\(session.id).json"), options: .atomic)
            if let i = stored.firstIndex(where: { $0.id == session.id }) { stored[i] = session } else { stored.append(session) }
            if sending, session.isSendable { send(try Session.encoder.encode(session), id: session.id) } // an empty session in progress is never sent
            return true
        } catch {
            status = "No se pudo guardar: \(error.localizedDescription)"
            WKInterfaceDevice.current().play(.failure) // data at risk: the one haptic allowed outside the set loop
            return false
        }
    }

    /// `final`: the Watch won't write this session again (G70: after the note step, auto-end, or a relaunch).
    private func send(_ data: Data, id: String, final: Bool = false) {
        #if DEBUG
        if Demo.isOn { // no phone: -demoAcked plays the phone's ack at once, otherwise nothing is ever sent
            if let rev = try? Session.decoder.decode(Session.self, from: data).rev {
                if Demo.acked { acks.record(id: id, rev: rev) } else if Demo.onPhone { acks.deliver(id: id, rev: rev) }
            }
            return
        }
        #endif
        guard WCSession.default.activationState == .activated else { return } // resent on activation
        // Older revs of this session still queued are now useless; the phone keeps the highest anyway.
        for t in WCSession.default.outstandingUserInfoTransfers where t.userInfo["id"] as? String == id { t.cancel() }
        WCSession.default.transferUserInfo(final ? ["id": id, "session": data, "final": true] : ["id": id, "session": data])
    }

    private func setPlan(_ plan: Plan) {
        inbox.receive(plan, sessionOpen: session != nil)
        if currentSlot == nil, let key = routineKey { // relaunch mid-session: the Watch proposes where to go on
            currentSlot = self.plan?.firstPendingSlot(routineKey: key, session: session, added: addedSets)
            autoPicked = true
            syncDraft()
            publishLive()
        }
    }

    // MARK: Live state to the phone (G15)

    /// What the phone's AirPods cues and lock-screen panel follow: the countdown, then the running session.
    private var liveState: LiveState? {
        LiveState.watch(plan: plan, routineKey: session == nil ? countdown?.routineKey : routineKey, session: session,
                        slot: currentSlot, added: addedSets, draft: draft, restStart: restStart, restEnd: restEnd,
                        go: countdown.map { $0.began.addingTimeInterval(TimeInterval(Countdown.seconds)) })
    }

    /// Sends the live state once the current action is done (one message per action, after its haptic).
    /// Never per Crown detent (G25): the Crown publishes once, when it settles (`crownSettled`).
    private func publishLive() {
        guard !livePending else { return }
        livePending = true
        Task { sendLive() }
    }

    /// Sends the live state now if it differs from the last one the phone got. Only a delivered state counts as
    /// sent (LA-01): a failed send is retried once after 1 s if nothing newer went out, and otherwise the next
    /// publish resends the latest state. A send while mirroring is down fails; mirroring coming up resends.
    private func sendLive(ended: Bool = false, retry: Bool = true) {
        livePending = false
        guard var state = liveState, let hkSession else { return }
        if ended { state.ended = true }
        guard state != liveSent, state != liveInFlight || !retry, let data = try? state.encoded() else { return }
        liveSeq += 1
        liveInFlight = state // an identical publish while this one flies is not sent twice (a rest tick could play twice)
        let seq = liveSeq, sent = state
        hkSession.sendToRemoteWorkoutSession(data: data) { ok, _ in
            Task { @MainActor in
                guard seq == self.liveSeq else { return } // a newer send owns the outcome
                self.liveInFlight = nil
                if ok { self.liveSent = sent; return self.publishLive() } // state moved back while in flight (un-log → Deshacer)
                guard retry else { return }
                try? await Task.sleep(for: .seconds(1))
                if seq == self.liveSeq { self.sendLive(ended: ended, retry: false) }
            }
        }
    }

    /// Start from iPhone (G15): the phone's WatchConnectivity request…
    func phoneRequested(routineKey: String, at: Date) {
        if let key = phoneStart.requested(routineKey, at: at, now: .now) { beginCountdown(routineKey: key) }
    }

    /// …and its launch of the app with a workout configuration. Both, in any order, start the countdown.
    func phoneLaunched() {
        if let key = phoneStart.launched(now: .now) { beginCountdown(routineKey: key) }
    }

    // MARK: Files (every session stays on the Watch: Documents/sessions/<id>.json)

    private static var sessionsDir: URL {
        #if DEBUG
        if Demo.isOn { return URL.documentsDirectory.appending(path: "demo-sessions") }
        #endif
        return URL.documentsDirectory.appending(path: "sessions")
    }

    /// Every session file, and how many `.json` files won't decode: those are counted, never dropped (SY-02).
    // lean: every session file is read at launch; prune old acked files if this ever gets slow.
    private static func allSessions() -> (sessions: [Session], unreadable: Int) {
        let files = ((try? FileManager.default.contentsOfDirectory(at: sessionsDir, includingPropertiesForKeys: nil)) ?? [])
            .filter { $0.pathExtension == "json" }
        let sessions = files.compactMap { try? Session.decoder.decode(Session.self, from: Data(contentsOf: $0)) }
        return (sessions, files.count - sessions.count)
    }

    /// Resends every non-empty session whose latest rev the phone hasn't acked (from the files as saved on disk), never
    /// a rev the phone wrote (G70). A finished session outside the summary goes as final.
    private func resendUnsent() {
        for s in acks.resend(stored) {
            if let data = try? Session.encoder.encode(s) { send(data, id: s.id, final: s.endedAt != nil && s.id != finished?.session.id) }
        }
    }

    /// At launch (G70, relaunch of a finished session): every session finished in the last 24 h goes once more with
    /// `final: true`, so the phone may edit it even if the app died in the summary. Acked ones too: the flag is the news.
    // lean: re-sent on every launch while inside the 24 h window (one or two sessions); track "final sent" if that grows.
    private func sendFinals() {
        for s in acks.finals(stored, now: .now) where s.id != finished?.session.id { // G85: confirmed ones only
            sendFinal(s.id)
        }
    }

    // MARK: Sync button (G51)

    /// "Sincronizar ahora": always tried, whatever the reachability says (SY-06). Joins a sync already out instead of
    /// sending a second one, so a tap during an auto-sync never doubles the request.
    func syncNow() {
        syncResult = nil
        syncManual = true
        if !syncing { startSync() }
    }

    /// "Reiniciar conexión" (G98c), outside a session only: what a relaunch would do, without quitting (Apple: never
    /// `exit()`). Reloads the session files and acks from disk, re-activates WatchConnectivity (its activation handler
    /// re-applies the plan + theme the phone left and resends), then "Sincronizar ahora", which resends every
    /// unconfirmed session and shows the iPhone's reply. Deletes nothing. Can't fix the phone's "no ve el reloj".
    func restartConnection() {
        guard session == nil, !syncing else { return }
        #if DEBUG
        if Demo.isOn { return syncNow() } // no phone, demo files: only the sync and its demo reply
        #endif
        (stored, unreadable) = Self.allSessions()
        acks = Self.loadAcks()
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
        syncNow()
    }

    /// Auto-sync (G51): when the routine list opens (at most every 15 min) and right after Terminar (`force`), only
    /// while the phone is reachable. No spin, no result line: nothing moves unless the athlete asked.
    func autoSync(force: Bool = false) {
        guard !syncing, session == nil, WCSession.isSupported(), WCSession.default.activationState == .activated,
              WCSession.default.isReachable, force || AutoSync.due(last: lastSyncAttempt, now: .now) else { return }
        startSync()
    }

    /// Re-queues what isn't confirmed and asks the phone to refresh (snapshot + flush); the reply, an error or 20 s of
    /// silence ends it. Only the newest request's outcome counts (`syncSeq`). The plan time never moves here (SY-11).
    private func startSync() {
        syncing = true
        lastSyncAttempt = .now
        syncSeq += 1
        let seq = syncSeq
        #if DEBUG
        if Demo.isOn { // no phone: the reply the demo flags ask for, after a few seconds
            Task { try? await Task.sleep(for: .seconds(4)); endSync(seq, Demo.syncReply) }
            return
        }
        #endif
        resendUnsent()
        Task { await syncDirect() } // G103: the Worker directly, whatever the phone answers
        guard WCSession.default.activationState == .activated else { return endSync(seq, .noReply) }
        WCSession.default.sendMessage(["sync": true], replyHandler: { @Sendable reply in
            let result = SyncResult(reply: reply)
            Task { @MainActor in self.endSync(seq, result) }
        }, errorHandler: { @Sendable _ in
            Task { @MainActor in self.endSync(seq, .noReply) }
        })
        Task {
            try? await Task.sleep(for: .seconds(AutoSync.timeout))
            endSync(seq, .noReply) // "El iPhone no responde"; a reply that already came makes this a no-op
        }
    }

    private func endSync(_ seq: Int, _ result: SyncResult) {
        guard seq == syncSeq, syncing else { return }
        syncing = false
        if syncManual { syncResult = result }
        syncManual = false
    }

    // MARK: Direct to the Worker (G103)

    /// Launch and "Sincronizar ahora": finished sessions up, then the plan down.
    private func syncDirect() async {
        await uploadDirect()
        await fetchPlanDirect()
    }

    /// PUTs the Watch's finished sessions to the Worker itself (system routing: the iPhone's Bluetooth, known Wi-Fi or
    /// LTE), so a session never waits for the phone link. The phone still relays the same revs; the Worker keeps the
    /// highest rev, so the copies are harmless. Read like the phone's flush; a failure stops until the next try
    /// (launch, Terminar, final, Sincronizar).
    func uploadDirect() async {
        guard !uploading, !isPreview, let token = Keychain.read() else { return }
        #if DEBUG
        if Demo.isOn { return }
        #endif
        uploading = true
        defer { uploading = false }
        for s in acks.uploads(stored, now: .now) {
            guard let body = try? Session.encoder.encode(s),
                  let (_, resp) = try? await URLSession.shared.data(for: Server.request("api/workout/session", method: "PUT",
                                                                                         body: body, token: token))
            else { return }
            switch UploadReply(status: (resp as? HTTPURLResponse)?.statusCode ?? 0) {
            case .accepted: recordAck(id: s.id, rev: s.rev)
            case .refused: recordReject(id: s.id, rev: s.rev)
            case .signedOut: return Keychain.delete()
            case .retry: return
            }
        }
    }

    /// Reads the published plan itself, with the phone's checks (schema major, a plan in it). A failure keeps the plan.
    private func fetchPlanDirect() async {
        guard !isPreview, let token = Keychain.read() else { return }
        #if DEBUG
        if Demo.isOn { return }
        #endif
        guard let (data, resp) = try? await URLSession.shared.data(for: Server.request("api/snapshot/latest", token: token))
        else { return }
        let code = (resp as? HTTPURLResponse)?.statusCode
        if code == 401 { return Keychain.delete() }
        guard code == 200, let v = EntrenoSnapshot.schemaVersion(of: data), EntrenoSnapshot.isSupported(v),
              let envelope = try? Plan.decoder.decode(SnapshotEnvelope.self, from: data), let plan = envelope.payload.workout,
              !isOlder(envelope.publishedAt) else { return }
        setPlan(plan)
        planCheckedAt = .now
        planPublishedAt = envelope.publishedAt
    }

    /// The plan comes two ways now (phone context, direct read): an older publish never replaces a newer one.
    private func isOlder(_ published: String?) -> Bool {
        guard let published, let current = planPublishedAt else { return false }
        return published < current // ISO 8601 from the same server: text order is time order
    }

    // MARK: Acks (UserDefaults)

    private static func loadAcks() -> Acks {
        UserDefaults.standard.data(forKey: "acks").flatMap { try? JSONDecoder().decode(Acks.self, from: $0) } ?? Acks()
    }

    private func recordAck(id: String, rev: Int) {
        acks.record(id: id, rev: rev)
        UserDefaults.standard.set(try? JSONEncoder().encode(acks), forKey: "acks")
    }

    /// WatchConnectivity handed this rev to the iPhone (G99): "En el iPhone" until the server's ack arrives.
    private func recordDelivered(id: String, rev: Int) {
        acks.deliver(id: id, rev: rev)
        UserDefaults.standard.set(try? JSONEncoder().encode(acks), forKey: "acks")
    }

    /// The Worker refused this rev (phone "Rechazada"): shown on the routine list and Resumen, not re-sent.
    private func recordReject(id: String, rev: Int) {
        acks.reject(id: id, rev: rev)
        UserDefaults.standard.set(try? JSONEncoder().encode(acks), forKey: "acks")
    }

    /// The athlete dismissed that refused rev on the phone: the sync button stops flagging it (SY-09).
    private func recordDismiss(id: String, rev: Int) {
        acks.dismiss(id: id, rev: rev)
        UserDefaults.standard.set(try? JSONEncoder().encode(acks), forKey: "acks")
    }

    // MARK: HealthKit

    /// Creates the strength workout and `prepare()`s it (sensors warm up) during the countdown.
    private func prepareWorkout() async {
        #if DEBUG
        if Demo.isOn { return } // no HealthKit prompt in demo mode
        #endif
        let config = HKWorkoutConfiguration()
        config.activityType = .traditionalStrengthTraining
        config.locationType = .indoor
        do {
            try await store.requestAuthorization(toShare: [HKObjectType.workoutType()],
                                                 read: [HKQuantityType(.heartRate), HKQuantityType(.activeEnergyBurned),
                                                        HKCharacteristicType(.dateOfBirth)])
            let s = try HKWorkoutSession(healthStore: store, configuration: config)
            let b = s.associatedWorkoutBuilder()
            b.dataSource = HKLiveWorkoutDataSource(healthStore: store, workoutConfiguration: config)
            attach(s, b)
            s.prepare()
            mirrorRetried = false
            startMirroring(s)
            if let dob = try? store.dateOfBirthComponents().date {
                age = Calendar.current.dateComponents([.year], from: dob, to: .now).year
            }
        } catch {
            status = "Salud: \(error.localizedDescription)" // the set log works without HealthKit
        }
    }

    /// At "go": starts the prepared workout at the session's start (waits if the permission prompt is still up).
    private func startPrepared(at start: Date) async {
        #if DEBUG
        if Demo.isOn { // fixed heart rate + a made-up curve for the Métricas screenshots
            heartRate = Demo.big ? 188 : Demo.heartRate
            heartRateAt = .distantFuture // the demo's reading never goes stale
            hrSamples = Demo.heartSeries(from: start, to: .now)
            activeKcal = Demo.big ? 999 : Demo.kcal(from: start)
            if Demo.big { Demo.fillBig(&session) }
            return
        }
        #endif
        await hkPrep?.value
        guard let hkSession, let builder else { return }
        hkSession.startActivity(with: start)
        do { try await builder.beginCollection(at: start) } catch { status = "Salud: \(error.localizedDescription)" }
    }

    /// Ends the workout without saving it to Apple Health.
    private func discardWorkout() {
        mirrorRetried = true
        if let hkSession, let builder {
            hkSession.end()
            builder.discardWorkout()
        }
        hkSession = nil
        builder = nil
        heartRate = nil
    }

    /// After a crash or relaunch mid-session, re-attach to the workout HealthKit kept running.
    private func recoverWorkout() async {
        guard let s = try? await store.recoverActiveWorkoutSession() else { return }
        attach(s, s.associatedWorkoutBuilder())
        startMirroring(s) // the SDK doesn't say whether mirroring survives a relaunch, and there's no "is mirroring" to ask
        await refillHeartRate()
    }

    /// After a relaunch the graph, averages, zones and recovery would start from now under whole-session labels (red
    /// team MT-04): one query for the session's heart rate since its start, merged before what came in meanwhile.
    private func refillHeartRate() async {
        guard let start = session?.startedAt else { return }
        let query = HKSampleQueryDescriptor(
            predicates: [.quantitySample(type: HKQuantityType(.heartRate), predicate: HKQuery.predicateForSamples(withStart: start, end: nil))],
            sortDescriptors: [SortDescriptor(\.endDate)])
        guard let found = try? await query.result(for: store), !found.isEmpty else { return } // "desde hh:mm" covers it (`hrSince`)
        let old = found.map { HRSample(t: $0.endDate, bpm: $0.quantity.doubleValue(for: .count().unitDivided(by: .minute()))) }
        hrSamples = old + hrSamples.filter { $0.t > old.last!.t }
    }

    private func attach(_ s: HKWorkoutSession, _ b: HKLiveWorkoutBuilder) {
        s.delegate = self
        b.delegate = self
        hkSession = s
        builder = b
    }

    /// Ends and SAVES the workout to Apple Health.
    private func endWorkout(at end: Date, id: String) async {
        guard let hkSession, let builder else { return }
        mirrorRetried = true
        hkSession.end()
        // G91: the session id on the Health workout, so a later version can delete exactly this one. Never blocks the save.
        try? await builder.addMetadata([HKMetadataKeyExternalUUID: id])
        do {
            try await builder.endCollection(at: end)
            try await builder.finishWorkout()
        } catch {
            status = "Salud: \(error.localizedDescription)"
        }
        self.hkSession = nil
        self.builder = nil
        heartRate = nil
    }

    /// G59: the iPhone app opened with no mirrored workout (a force-quit app is never relaunched by the first mirror).
    /// User-triggered, so it tries once per app open and leaves `mirrorRetried` (the disconnect retry) alone.
    func phoneOpened() {
        guard let session, session.endedAt == nil, let hkSession else { return }
        Task {
            do {
                try await hkSession.startMirroringToCompanionDevice()
            } catch {
                // HKWorkoutSession.h doesn't say what a second start does on a session still mirrored to a killed app,
                // and there's no "is mirroring" to ask: stop it, then start again. Quiet: the next app open retries.
                try? await hkSession.stopMirroringToCompanionDevice()
                guard (try? await hkSession.startMirroringToCompanionDevice()) != nil else { return }
            }
            guard hkSession === self.hkSession else { return } // the workout ended meanwhile
            liveSent = nil // the phone gets the current state once mirroring is up
            sendLive()
        }
    }

    /// Mirrors the workout to the iPhone (G15) so its app runs in the pocket (AirPods cues, lock-screen panel).
    /// Off the HealthKit start path; a failure is a status line, the set log never depends on it.
    private func startMirroring(_ s: HKWorkoutSession) {
        Task {
            do {
                try await s.startMirroringToCompanionDevice()
                liveSent = nil // the phone gets the current state once mirroring is up
                sendLive()
            } catch {
                if !status.hasPrefix("No se pudo guardar") { status = "iPhone: \(error.localizedDescription)" }
            }
        }
    }
}

extension WatchModel: HKWorkoutSessionDelegate {
    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession, didChangeTo toState: HKWorkoutSessionState,
                                    from fromState: HKWorkoutSessionState, date: Date) {}

    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession, didFailWithError error: Error) {
        Task { @MainActor in
            if !self.status.hasPrefix("No se pudo guardar") { self.status = "Salud: \(error.localizedDescription)" } // data at risk wins
        }
    }

    /// The phone dropped off the mirrored workout: one retry while the workout runs.
    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession, didDisconnectFromRemoteDeviceWithError error: Error?) {
        Task { @MainActor in
            guard workoutSession === self.hkSession, !self.mirrorRetried else { return }
            self.mirrorRetried = true
            self.startMirroring(workoutSession)
        }
    }
}

extension WatchModel: HKLiveWorkoutBuilderDelegate {
    nonisolated func workoutBuilder(_ workoutBuilder: HKLiveWorkoutBuilder, didCollectDataOf collectedTypes: Set<HKSampleType>) {
        let hr = collectedTypes.contains(HKQuantityType(.heartRate))
            ? workoutBuilder.statistics(for: HKQuantityType(.heartRate)) : nil
        let bpm = hr?.mostRecentQuantity()?.doubleValue(for: .count().unitDivided(by: .minute()))
        let at = hr?.mostRecentQuantityDateInterval()?.end ?? .now
        let kcal = collectedTypes.contains(HKQuantityType(.activeEnergyBurned))
            ? workoutBuilder.statistics(for: HKQuantityType(.activeEnergyBurned))?.sumQuantity()?.doubleValue(for: .kilocalorie())
            : nil
        Task { @MainActor in
            if let bpm {
                self.heartRate = bpm
                self.heartRateAt = at
                if self.hrSamples.last?.t != at { self.hrSamples.append(HRSample(t: at, bpm: bpm)) }
            }
            if let kcal { self.activeKcal = kcal }
        }
    }

    nonisolated func workoutBuilderDidCollectEvent(_ workoutBuilder: HKLiveWorkoutBuilder) {}
}

extension WatchModel: WCSessionDelegate {
    nonisolated func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {
        let context = Context(session.receivedApplicationContext)
        Task { @MainActor in
            self.apply(context)
            self.resendUnsent()
            self.sendFinals()
            self.autoSync() // the routine list opened at launch, before WatchConnectivity was up
        }
    }

    nonisolated func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        if let key = userInfo["start"] as? String, let at = userInfo["at"] as? Date { // start from iPhone (G15)
            Task { @MainActor in self.phoneRequested(routineKey: key, at: at) }
            return
        }
        if let at = userInfo["phoneOpen"] as? Date { // G59 queued fallback; a late one is ignored
            if PhoneOpen.isFresh(sentAt: at, now: .now) { Task { @MainActor in self.phoneOpened() } }
            return
        }
        if let data = userInfo["adopt"] as? Data { // G70: the phone's edit of a finished session
            Task { @MainActor in self.adopt(data) }
            return
        }
        if let reply = SwapReply(userInfo) { Task { @MainActor in self.swapReplied(id: reply.id, templateId: reply.templateId, name: reply.name) } }
        guard let rev = userInfo["rev"] as? Int else { return }
        if let id = userInfo["ack"] as? String { Task { @MainActor in self.recordAck(id: id, rev: rev) } }
        if let id = userInfo["rejected"] as? String { Task { @MainActor in self.recordReject(id: id, rev: rev) } }
        if let id = userInfo["dismissed"] as? String { Task { @MainActor in self.recordDismiss(id: id, rev: rev) } }
    }

    /// A session transfer reached the iPhone (G99): the phone has that rev even if it can't reach the server yet.
    nonisolated func session(_ session: WCSession, didFinish userInfoTransfer: WCSessionUserInfoTransfer, error: Error?) {
        guard error == nil, let id = userInfoTransfer.userInfo["id"] as? String,
              let data = userInfoTransfer.userInfo["session"] as? Data,
              let rev = try? Session.decoder.decode(Session.self, from: data).rev else { return }
        Task { @MainActor in self.recordDelivered(id: id, rev: rev) }
    }

    nonisolated func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        if message["phoneOpen"] as? Bool == true { Task { @MainActor in self.phoneOpened() } } // G59
        if let reply = SwapReply(message) { Task { @MainActor in self.swapReplied(id: reply.id, templateId: reply.templateId, name: reply.name) } }
    }

    /// The phone's pick for "Otro (en el iPhone)" (G69): `["swapReply": request id, "templateId", "name"]`, by message
    /// or user info.
    struct SwapReply: Sendable {
        let id: String
        let templateId: String
        let name: String
        nonisolated init?(_ d: [String: Any]) {
            guard let id = d["swapReply"] as? String, let t = d["templateId"] as? String, let n = d["name"] as? String,
                  !t.isEmpty, !n.isEmpty else { return nil }
            (self.id, templateId, name) = (id, t, n)
        }
    }

    nonisolated func session(_ session: WCSession, didReceiveApplicationContext context: [String: Any]) {
        let context = Context(context)
        Task { @MainActor in self.apply(context) }
    }

    /// The phone's application context, decoded off the main actor: the plan, its check time and publish date (only
    /// when they come with a plan, SY-11) and the theme (G43: "magenta" | "neon").
    struct Context: Sendable {
        let plan: Plan?
        let checkedAt: Date?
        let publishedAt: String?
        let theme: String?
        /// The owner token for the direct path (G103); "" = signed out, nil = not in this context.
        let token: String?
        let gyms: Data?

        nonisolated init(_ c: [String: Any]) {
            plan = (c["plan"] as? Data).flatMap { try? Plan.decoder.decode(Plan.self, from: $0) }
            checkedAt = plan == nil ? nil : c["syncedAt"] as? Date
            publishedAt = plan == nil ? nil : c["publishedAt"] as? String
            theme = c["theme"] as? String
            token = c["ownerToken"] as? String
            gyms = c["gyms"] as? Data
        }
    }

    private func apply(_ c: Context) {
        if let data = c.gyms, let g = try? JSONDecoder().decode(Gyms.self, from: data) {
            gyms = g
            UserDefaults.standard.set(data, forKey: "gyms")
        }
        if let token = c.token, token != Keychain.read() ?? "" {
            if token.isEmpty { Keychain.delete() } else { Keychain.save(token); Task { await syncDirect() } }
        }
        if let plan = c.plan, !isOlder(c.publishedAt) {
            setPlan(plan)
            planCheckedAt = c.checkedAt
            planPublishedAt = c.publishedAt
        }
        if let theme = c.theme { receiveTheme(theme) }
    }
}

extension Array {
    subscript(safe i: Int) -> Element? { indices.contains(i) ? self[i] : nil }
}

extension Plan.Slot {
    /// What fits the 42 mm Watch: the coach's short name, else the full one (Q26). VoiceOver labels use `name`.
    var short: String { shortName ?? name }
}
