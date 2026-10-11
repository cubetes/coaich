import Foundation

/// One performance of a routine: the wire document of `docs/contracts/workout-session.v1.md`.
/// Encode/decode with `Session.encoder` / `Session.decoder` (snake_case, ISO-8601 UTC `Z`).
public struct Session: Codable, Sendable, Equatable, Identifiable {
    public let id: String
    public var rev: Int
    public let routineTitle: String
    public let startedAt: Date
    public var endedAt: Date?
    public var exercises: [Exercise]
    /// The athlete's note after Terminar ("¿Cómo ha ido?", G42; contract v1.1): trimmed, ≤ `maxNote` code points,
    /// absent when there is none.
    public var note: String?
    /// The gym this session was trained in (G92; contract v1.2): a slug `[a-z0-9-]{1,40}` from the gym list, absent
    /// when nil. Nothing stamps it yet (v0.8.0); it is carried through every rev so a stamped session keeps it.
    public var gymId: String?
    /// Watch-only state kept in the Watch's session file so a relaunch mid-session keeps it (G79, red team MT-02/MT-04):
    /// sets added with "+1 serie" per slot, and the rest-timer windows. Written only by `fileEncoder`, never sent: the
    /// contract document stays as it was. nil in older files and in every document from the wire.
    public var addedSets: [String: Int]?
    public var rests: [DateInterval]?

    public struct Exercise: Codable, Sendable, Equatable {
        public let slot: String
        public let exerciseTemplateId: String
        public let title: String
        public let substituted: Bool
        public var sets: [SetEntry]
        /// The athlete's note on this exercise (G95; contract v1.2 `exercises[].note`): trimmed, ≤ `maxExerciseNote`
        /// code points, absent when there is none (synthesized `encodeIfPresent`). Set with `setExerciseNote`.
        public var note: String? = nil
    }

    public struct SetEntry: Codable, Sendable, Equatable {
        public var index: Int
        public var type: SetType
        public var weightKg: Double
        public var reps: Int
        public var rir: Int?
        public var unedited: Bool
        public let doneAt: Date

        public func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(index, forKey: .index)
            try c.encode(type, forKey: .type)
            try c.encode(weightKg, forKey: .weightKg)
            try c.encode(reps, forKey: .reps)
            try c.encode(rir, forKey: .rir) // contract: explicit null, not omitted
            try c.encode(unedited, forKey: .unedited)
            try c.encode(doneAt, forKey: .doneAt)
        }
    }

    public enum SetType: String, Codable, Sendable {
        case warmup, normal, failure, dropset
    }

    public init(id: String = UUID().uuidString.lowercased(), routineTitle: String, startedAt: Date) {
        self.id = id
        self.rev = 1
        self.routineTitle = routineTitle
        self.startedAt = startedAt
        self.endedAt = nil
        self.exercises = []
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(rev, forKey: .rev)
        try c.encode(routineTitle, forKey: .routineTitle)
        try c.encode(startedAt, forKey: .startedAt)
        try c.encode(endedAt, forKey: .endedAt) // contract: explicit null while in progress
        try c.encode(exercises, forKey: .exercises)
        try c.encodeIfPresent(note, forKey: .note) // v1.1: only when there is one, so v1 documents stay byte-identical
        try c.encodeIfPresent(gymId, forKey: .gymId) // v1.2: same rule
        if encoder.userInfo[Self.fileKey] as? Bool == true {
            try c.encodeIfPresent(addedSets, forKey: .addedSets)
            try c.encodeIfPresent(rests, forKey: .rests)
        }
    }

    public static let maxNote = 1000

    /// Sets the note (G42): trimmed and capped at `maxNote` Unicode code points (the Worker's limit); blank clears it. New rev when it changed, so
    /// the finished session goes out again with it.
    public mutating func setNote(_ text: String?) {
        let new = Self.clean(text, max: Self.maxNote)
        guard new != note else { return }
        note = new
        rev += 1
    }

    public static let maxExerciseNote = 500

    /// The note on a slot's exercise (G95), by `setNote`'s rule at `maxExerciseNote` code points. It goes on the slot's
    /// current entry (the substitute after a swap); a slot with no logged set holds no note (refused). New rev when it
    /// changed. Un-logging every set of that exercise drops the note (`deleteSet`).
    @discardableResult
    public mutating func setExerciseNote(_ text: String?, slot: String) -> Bool {
        guard let i = entries(slot).last(where: { !exercises[$0].sets.isEmpty }) else { return false }
        let new = Self.clean(text, max: Self.maxExerciseNote)
        guard new != exercises[i].note else { return true }
        exercises[i].note = new
        rev += 1
        return true
    }

    /// Trimmed and cut at `max` Unicode code points (the Worker counts them and refuses more with a 400 that refuses
    /// the whole session); blank = nil.
    private static func clean(_ text: String?, max: Int) -> String? {
        let t = (text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let capped = String(String.UnicodeScalarView(t.unicodeScalars.prefix(max))).trimmingCharacters(in: .whitespacesAndNewlines)
        return capped.isEmpty ? nil : capped
    }

    /// Positions in `exercises` of the slot's entries, in order: more than one after a substitution mid-slot (ADR 0003).
    private func entries(_ slot: String) -> [Int] { exercises.indices.filter { exercises[$0].slot == slot } }

    /// Confirmed sets already logged for a slot, across a substitution. Each `index` is the set's position in the slot
    /// (S1…Sn keep counting after a swap, and every slot-level `index:` below means this); the wire `index` stays
    /// per exercise.
    public func sets(forSlot slot: String) -> [SetEntry] {
        entries(slot).flatMap { exercises[$0].sets }.enumerated().map { var set = $1; set.index = $0; return set }
    }

    /// The exercise the slot's next set goes to: the latest entry (a substitute after a swap); nil = the plan's own,
    /// nothing logged or swapped yet.
    public func currentExercise(forSlot slot: String) -> Exercise? {
        entries(slot).last.map { exercises[$0] }
    }

    /// (entry, set) for a slot-level set position.
    private func locate(_ slot: String, _ index: Int) -> (Int, Int)? {
        guard index >= 0 else { return nil }
        var n = index
        for i in entries(slot) {
            if n < exercises[i].sets.count { return (i, n) }
            n -= exercises[i].sets.count
        }
        return nil
    }

    /// Records a confirmed set (ADR 0001): whatever is shown is what was lifted; `unedited`
    /// says whether it still equals the pre-fill. New exercises append in the order done.
    public mutating func confirm(slot: String, templateId: String, title: String,
                                 planned: PlannedSet, weightKg: Double, reps: Int,
                                 type: SetType = .normal, at: Date) {
        guard endedAt == nil else { return } // never after Terminar: the summary and the note's rev are built on it
        append(slot: slot, templateId: templateId, title: title, weightKg: weightKg, reps: reps, type: type,
               unedited: planned.weightKg == weightKg && planned.reps == reps, at: at)
    }

    /// Phone edit (Q20): a set the Watch missed, added at the end of the slot — also on a finished session, which
    /// stays finished (`ended_at` kept). Never pre-filled, so never `unedited`. Out-of-range values (`Entry`) or a
    /// full exercise/session (`canLog`) are refused.
    @discardableResult
    public mutating func addSet(slot: String, templateId: String, title: String, weightKg: Double, reps: Int,
                                type: SetType = .normal, at: Date) -> Bool {
        guard Entry.kg.contains(weightKg), Entry.reps.contains(reps), canLog(slot: slot) == nil else { return false }
        append(slot: slot, templateId: templateId, title: title, weightKg: weightKg, reps: reps, type: type,
               unedited: false, at: at)
        return true
    }

    /// Phone edit (G70, red team ED-05): a missed set added to one exercise entry (`position` in `exercises`) — after a
    /// swap the slot has two, and the set goes under the one it was lifted on. Same rules as `addSet(slot:…)`: never
    /// `unedited`, bounds, 30 sets per exercise, `ended_at` kept.
    @discardableResult
    public mutating func addSet(exercise position: Int, weightKg: Double, reps: Int, type: SetType = .normal, at: Date) -> Bool {
        guard exercises.indices.contains(position), Entry.kg.contains(weightKg), Entry.reps.contains(reps),
              exercises[position].sets.count < Self.maxSets else { return false }
        exercises[position].sets.append(SetEntry(index: exercises[position].sets.count, type: type, weightKg: weightKg,
                                                 reps: reps, rir: nil, unedited: false, doneAt: at))
        rev += 1
        return true
    }

    /// Adds to the slot's current exercise (the substitute after a swap); a slot new to the session appends one.
    private mutating func append(slot: String, templateId: String, title: String, weightKg: Double, reps: Int,
                                 type: SetType, unedited: Bool, at: Date) {
        if let i = entries(slot).last {
            exercises[i].sets.append(SetEntry(index: exercises[i].sets.count, type: type, weightKg: weightKg,
                                              reps: reps, rir: nil, unedited: unedited, doneAt: at))
        } else {
            exercises.append(Exercise(slot: slot, exerciseTemplateId: templateId, title: title, substituted: false,
                                      sets: [SetEntry(index: 0, type: type, weightKg: weightKg, reps: reps,
                                                      rir: nil, unedited: unedited, doneAt: at)]))
        }
        rev += 1
    }

    /// Swaps the slot's exercise for the sets logged from now on (Q13/Q22, ADR 0003): the slot key stays, sets
    /// already logged keep their exercise, the next set goes to a new entry with `templateId` and `substituted`
    /// (true unless it is the plan's own `planned` template again). The new entry has no sets until one is logged,
    /// so no new rev and nothing to send yet. Swapping an unused swap replaces it; swapping back to the exercise in
    /// use before it undoes it. Refused after Terminar, onto the exercise already current, or past 40 exercises.
    @discardableResult
    public mutating func substitute(slot: String, templateId: String, title: String, planned: String) -> Bool {
        guard endedAt == nil, templateId != (currentExercise(forSlot: slot)?.exerciseTemplateId ?? planned)
        else { return false }
        if let last = entries(slot).last, exercises[last].sets.isEmpty { exercises.remove(at: last) }
        if templateId == (currentExercise(forSlot: slot)?.exerciseTemplateId ?? planned) { return true }
        guard exercises.count < Self.maxExercises else { return false }
        exercises.append(Exercise(slot: slot, exerciseTemplateId: templateId, title: title,
                                  substituted: templateId != planned, sets: []))
        return true
    }

    /// Takes back a swap while no set is logged on it yet; the slot goes back to the exercise before it.
    @discardableResult
    public mutating func undoSubstitution(slot: String) -> Bool {
        let e = entries(slot)
        guard endedAt == nil, let last = e.last, exercises[last].sets.isEmpty,
              exercises[last].substituted || e.count > 1 else { return false }
        exercises.remove(at: last)
        return true
    }

    /// No confirmed set right now.
    public var isEmpty: Bool { exercises.allSatisfy { $0.sets.isEmpty } }

    /// Finishing throws the session away (no file, no Health workout, nothing sent): it never had a set
    /// (`rev` 1 — every change bumps it). A session emptied by un-logging is finished and sent instead (N9).
    public var finishDiscards: Bool { isEmpty && rev == 1 }

    /// Whether this document goes to the phone: any session with a set, and a finished one emptied by
    /// un-logging (N9) — an earlier rev with the set may already be on the server, and the emptied, finished
    /// doc (0 exercises, allowed by the contract) replaces it, so the pull writes no rows for it.
    /// An empty session still in progress is never sent.
    public var isSendable: Bool { !isEmpty || endedAt != nil }

    /// The time of the last thing the athlete logged: the newest set, else the session start.
    public var lastActivity: Date {
        exercises.flatMap(\.sets).map(\.doneAt).max() ?? startedAt
    }

    /// Reps in reserve (0–3, 3 = "3 or more") on a confirmed set. A chip tap always selects; tapping the selected
    /// chip again keeps it (no silent clear, red team RT-12). `nil` clears it: only the set menu's "Quitar RIR".
    public mutating func setRIR(_ rir: Int?, slot: String, index: Int) {
        edit(slot: slot, index: index) { $0.rir = rir.map { min(max($0, 0), 3) } }
    }

    /// The contract's caps (`workout-session.v1.md`): the Worker refuses a document past them, so the Watch stops
    /// at them (audit #8).
    public static let maxSets = 30
    public static let maxExercises = 40

    public enum Cap: Equatable, Sendable { case sets, exercises }

    /// Why one more set can't be logged on this slot (nil = it can).
    public func canLog(slot: String) -> Cap? {
        guard let ex = currentExercise(forSlot: slot) else {
            return exercises.count >= Self.maxExercises ? .exercises : nil
        }
        return ex.sets.count >= Self.maxSets ? .sets : nil // per exercise: a substitute has its own 30
    }

    /// The 24 h edit window (Q20, G70): a session finished at most 24 h ago can be edited on the phone; after that it
    /// is locked. Never while in progress (red team ED-01: the Watch is still writing revs). Editing never re-opens it.
    public static let editWindow: TimeInterval = 24 * 3600
    public func isEditable(now: Date) -> Bool {
        endedAt.map { now.timeIntervalSince($0) <= Self.editWindow } ?? false
    }

    /// Edits a confirmed set in place (Watch "Guardar"): same index and `doneAt`, new rev when anything
    /// changed. A kg or reps change clears `unedited`. Out-of-range values (see `Entry`) are refused.
    @discardableResult
    public mutating func editSet(slot: String, index: Int, weightKg: Double, reps: Int, type: SetType) -> Bool {
        guard Entry.kg.contains(weightKg), Entry.reps.contains(reps) else { return false }
        edit(slot: slot, index: index) {
            if $0.weightKg != weightKg || $0.reps != reps { $0.unedited = false }
            $0.weightKg = weightKg
            $0.reps = reps
            $0.type = type
        }
        return true
    }

    public mutating func setType(_ type: SetType, slot: String, index: Int) {
        edit(slot: slot, index: index) { $0.type = type }
    }

    /// Deletes a confirmed set (slot-level position) and renumbers its exercise's sets from 0. An exercise left with
    /// no sets is dropped — except, while in progress, the slot's latest entry when it is a swap (substituted, or after
    /// another entry): the next set still goes to it.
    public mutating func deleteSet(slot: String, index: Int) {
        guard let (i, j) = locate(slot, index) else { return }
        exercises[i].sets.remove(at: j)
        for k in exercises[i].sets.indices { exercises[i].sets[k].index = k }
        if exercises[i].sets.isEmpty { exercises[i].note = nil } // G95: no sets left, no note about them
        let e = entries(slot)
        let keep = endedAt == nil && i == e.last && (exercises[i].substituted || e.count > 1)
        if exercises[i].sets.isEmpty, !keep { exercises.remove(at: i) }
        rev += 1
    }

    /// What un-logging took out, so "Deshacer" can put it back exactly.
    public struct Unlogged: Equatable, Sendable {
        public let exercise: Exercise   // the exercise as it was, with the set still in it
        public let position: Int        // where the exercise sat in `exercises`
        public let index: Int           // the set's index inside that exercise (not the slot position)
    }

    /// "Registrada ✓" pressed: the set goes back to pending. Same as deleting it (renumbers, new rev, sent
    /// as usual), but returns what is needed to undo it.
    public mutating func unlog(slot: String, index: Int) -> Unlogged? {
        guard let (i, j) = locate(slot, index) else { return nil }
        let taken = Unlogged(exercise: exercises[i], position: i, index: j)
        deleteSet(slot: slot, index: index)
        return taken
    }

    /// "Deshacer": restores an un-logged set with its values, RIR, type, `unedited` and `done_at`, in its
    /// old place. Sets logged on the slot since then stay, after it. New rev (the undo is sent too).
    public mutating func restore(_ u: Unlogged) {
        let set = u.exercise.sets[u.index]
        func same(_ e: Exercise) -> Bool {
            e.slot == u.exercise.slot && e.exerciseTemplateId == u.exercise.exerciseTemplateId
                && e.substituted == u.exercise.substituted
        }
        let at = exercises.indices.contains(u.position) && same(exercises[u.position]) ? u.position : nil
        if let i = at ?? exercises.firstIndex(where: same) {
            exercises[i].sets.insert(set, at: min(u.index, exercises[i].sets.count))
            if exercises[i].note == nil { exercises[i].note = u.exercise.note } // a kept swap entry lost it with its last set
            for j in exercises[i].sets.indices { exercises[i].sets[j].index = j }
        } else {
            var ex = u.exercise
            ex.sets = [set]
            ex.sets[0].index = 0
            exercises.insert(ex, at: min(u.position, exercises.count))
        }
        rev += 1
    }

    private mutating func edit(slot: String, index: Int, _ change: (inout SetEntry) -> Void) {
        guard let (i, j) = locate(slot, index) else { return }
        var set = exercises[i].sets[j]
        change(&set)
        guard set != exercises[i].sets[j] else { return }
        exercises[i].sets[j] = set
        rev += 1
    }

    /// Terminar. A swap never used (an exercise with no sets) is dropped: the finished document holds only lifts.
    public mutating func finish(at: Date) {
        endedAt = at
        exercises.removeAll { $0.sets.isEmpty }
        rev += 1
    }

    public static var encoder: JSONEncoder {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        e.dateEncodingStrategy = .iso8601 // UTC with Z, whole seconds
        return e
    }

    private static let fileKey = CodingUserInfoKey(rawValue: "athleteos.sessionFile")!

    /// The Watch's own file: the wire document plus `addedSets` and `rests`.
    public static var fileEncoder: JSONEncoder {
        let e = encoder
        e.userInfo[fileKey] = true
        return e
    }

    public static var decoder: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .iso8601
        return d
    }
}

/// The Watch's record of which session revs the phone confirmed reached the Worker
/// (phone → Watch `["ack": id, "rev": n]`). Acks can arrive late or out of order: keep the highest.
/// The phone also reports a rev the Worker refused (`["rejected": id, "rev": n]`, audit #8): "Rechazada".
public struct Acks: Codable, Sendable, Equatable {
    public var revs: [String: Int] = [:]
    /// Refused rev per session; absent in acks saved before 0.3.5.
    public var rejected: [String: Int]?
    /// A refused rev the athlete dismissed on the phone ("Descartar" on its "Rechazadas" row, G51 / SY-09): the Watch
    /// keeps the file but stops flagging it. Absent before 0.5.0.
    public var dismissed: [String: Int]?
    /// A rev the phone wrote (24 h edit, G70) that the Watch stored from `["adopt": data]`: never sent back. Absent
    /// before 0.6.0.
    public var adopted: [String: Int]?
    /// Highest rev WatchConnectivity delivered to the iPhone (`didFinish userInfoTransfer`, G99): the phone has it,
    /// the server may not yet. Watch-only; absent before 0.7.2.
    public var delivered: [String: Int]?
    /// The rev the Watch sent with `final: true` (G70). Its own upload to the Worker stops there (G103): a later Watch
    /// rev is a post-final note, which goes through the phone only, so it merges over a phone edit instead of racing
    /// it for the same rev number. Watch-only; absent before 0.8.0.
    public var finalRev: [String: Int]?

    public init() {}

    public mutating func markFinal(id: String, rev: Int) {
        finalRev = (finalRev ?? [:]).merging([id: rev]) { max($0, $1) }
    }

    public mutating func record(id: String, rev: Int) {
        revs[id] = max(revs[id] ?? 0, rev)
    }

    public mutating func reject(id: String, rev: Int) {
        rejected = (rejected ?? [:]).merging([id: rev]) { max($0, $1) }
    }

    public mutating func dismiss(id: String, rev: Int) {
        dismissed = (dismissed ?? [:]).merging([id: rev]) { max($0, $1) }
    }

    public mutating func adopt(id: String, rev: Int) {
        adopted = (adopted ?? [:]).merging([id: rev]) { max($0, $1) }
    }

    public mutating func deliver(id: String, rev: Int) {
        delivered = (delivered ?? [:]).merging([id: rev]) { max($0, $1) }
    }

    /// The latest rev reached the iPhone (or the server, which only gets it through the phone, or it is the phone's own).
    public func isOnPhone(_ session: Session) -> Bool {
        (delivered?[session.id] ?? 0) >= session.rev || isSent(session) || isAdopted(session)
    }

    /// The Watch's copy is the phone's own rev: the phone has it, so the Watch never re-sends it.
    public func isAdopted(_ session: Session) -> Bool { adopted?[session.id] == session.rev }

    /// The latest rev was refused and not dismissed: the sync button's red state (G51).
    public func isProblem(_ session: Session) -> Bool {
        isRejected(session) && dismissed?[session.id] != session.rev
    }

    /// True when the session's latest rev reached the server ("Enviado ✓").
    public func isSent(_ session: Session) -> Bool {
        (revs[session.id] ?? 0) >= session.rev
    }

    /// True when the Worker refused the session's latest rev; a newer rev (an edit) goes out again. A higher rev
    /// confirmed since (the phone's fix, G70 / red team ED-04) clears it.
    public func isRejected(_ session: Session) -> Bool {
        rejected?[session.id] == session.rev && !isSent(session)
    }

    /// Sessions the Watch must (re)send: sendable, latest rev neither acked nor refused.
    public func unsent(_ sessions: [Session]) -> [Session] {
        sessions.filter { $0.isSendable && !isSent($0) && !isRejected($0) }
    }

    /// What the Watch re-sends at launch with `final: true` (G70, G85): sessions finished in the last 24 h whose latest
    /// rev the server confirmed — the flag is the news. An unconfirmed one already goes out (as final) with `resend`; a
    /// refused one never does, also once dismissed (bug: a dismissed refused session came back on every launch).
    public func finals(_ sessions: [Session], now: Date) -> [Session] {
        sessions.filter { $0.isEditable(now: now) && isSent($0) }
    }

    /// What the Watch re-sends: `unsent` minus the phone's own revs it adopted (G70).
    public func resend(_ sessions: [Session]) -> [Session] { unsent(sessions).filter { !isAdopted($0) } }

    /// What the Watch PUTs to the Worker itself (G103), oldest first: its own unconfirmed revs of sessions finished in
    /// the last 24 h, up to and including the final rev. Never a running session or an older one.
    // lean: a session sent as final before 0.8.0 has no `finalRev`, so for its last 24 h any Watch rev goes.
    public func uploads(_ sessions: [Session], now: Date) -> [Session] {
        resend(sessions).filter { $0.isEditable(now: now) && $0.rev <= finalRev?[$0.id] ?? $0.rev }
            .sorted { $0.startedAt < $1.startedAt }
    }
}
