import Foundation

/// The phone's store of sessions received from the Watch. Keeps the highest `rev` per session
/// and remembers which `rev` the Worker accepted, so nothing is lost and replays are harmless.
// lean: sent sessions are kept forever; prune entries older than ~90 days if the file passes ~1 MB.
public struct Outbox: Codable, Sendable, Equatable {
    public struct Item: Codable, Sendable, Equatable {
        public var session: Session
        public var sentRev: Int
        /// The Worker refused this rev (HTTP 400): parked with its error, shown as "Rechazada", never retried
        /// until a newer rev arrives. Absent in outboxes saved before 0.3.1.
        public var rejected: String?
        /// Highest rev received from the Watch; nil in outboxes saved before 0.6.0 (= the held rev, all the Watch's).
        public var watchRev: Int?
        /// The Watch sent its last rev (`final: true`, G70): it won't write this session again, so the phone may edit it.
        public var final: Bool?
        /// Deleted on the iPhone (G91): the session as it was before "Borrar sesión", kept so `restore` can bring it
        /// back exactly. The held `session` is then the emptied rev (0 exercises, no note) that tells the server.
        public var deleted: Session?

        /// The phone wrote the held rev (a 24 h edit, or a Watch note merged into one).
        var phoneOwned: Bool { session.rev > (watchRev ?? session.rev) }
    }

    public var items: [String: Item] = [:]
    /// Sessions the iPhone let go (G85): id → the last rev it held. A copy at or below it (a late or re-sent transfer)
    /// is ignored, so a dismissed or discarded session never comes back. Absent in outboxes saved before 0.7.1.
    // lean: kept forever (an id and an Int each); prune with the outbox if it ever grows.
    public var tombstones: [String: Int]?

    public init() {}

    /// Stores a Watch document if it is newer than what we hold. Returns true when the outbox changed.
    /// Once the phone has edited a finished session the writers are split (G70, red team ED-02): a later Watch rev
    /// brings only its `note`, merged into the phone's copy as a new rev above both, never dropped; a replay of a
    /// Watch rev already seen changes nothing.
    @discardableResult
    public mutating func receive(_ session: Session, final: Bool = false) -> Bool {
        if let dead = tombstones?[session.id], session.rev <= dead { return false }
        guard var held = items[session.id] else {
            items[session.id] = Item(session: session, sentRev: 0, watchRev: session.rev, final: final ? true : nil)
            return true
        }
        let seen = held.watchRev ?? held.session.rev
        let finalNews = final && held.final != true
        if final { held.final = true }
        guard session.rev > seen else { items[session.id] = held; return finalNews }
        if held.deleted != nil { // G91: the athlete deleted it here; a later Watch rev (a late note) never revives it
            held.watchRev = session.rev
            // Same rev number as the emptied one (or above): the Watch would keep its copy and never adopt the delete,
            // so the emptied rev goes out again above it.
            if session.rev >= held.session.rev { held.session.rev = session.rev + 1 }
            items[session.id] = held
            return true
        }
        if held.phoneOwned && held.session.endedAt != nil {
            held.watchRev = session.rev
            if session.note != held.session.note {
                held.session.note = session.note
                held.session.rev = max(held.session.rev, session.rev) + 1
                held.rejected = nil
            }
        } else {
            held = Item(session: session, sentRev: held.sentRev, watchRev: session.rev, final: held.final)
        }
        items[session.id] = held
        return true
    }

    /// The phone's 24 h edit (G70 "Guardar"): one new rev, held + 1, of a finished session it holds — sets and note
    /// (G78) together. The note follows the Watch's `setNote` rule (trimmed, ≤ 1000 code points, blank = none); editing
    /// waits for the Watch's final rev, so the phone owns it then. Returns the stored document, nil when refused or
    /// nothing changed.
    /// A set whose kg × reps end where they were keeps `unedited` (the phone's fields write every keystroke, so a
    /// retyped number passed through others, red team re-check RC-02).
    public mutating func save(edit: Session) -> Session? {
        guard var held = items[edit.id], held.deleted == nil, held.session.endedAt != nil, edit.endedAt != nil else { return nil }
        var doc = edit
        doc.keepUnedited(from: held.session)
        doc.note = held.session.note
        doc.setNote(edit.note) // its own rev bump is overwritten below: one rev per Guardar
        guard doc.exercises != held.session.exercises || doc.note != held.session.note else { return nil }
        doc.rev = held.session.rev + 1
        held.session = doc
        held.rejected = nil
        items[edit.id] = held
        return doc
    }

    /// "Editar" shows (G70): the Watch's final rev arrived and the session ended at most 24 h ago. The "Esperando al
    /// reloj…" gate stays (panel must-fix 18) although the note merge in `receive` already keeps the server copy safe:
    /// it also stops the Watch adopting a phone rev while its note screen still holds the older copy (ED-03).
    public func canEdit(id: String, now: Date) -> Bool {
        guard let item = items[id], item.final == true, item.deleted == nil, let end = item.session.endedAt else { return false }
        return now.timeIntervalSince(end) <= Session.editWindow
    }

    /// "Borrar sesión" shows (G91): a finished session the Watch is done with (its final rev arrived, or it ended more
    /// than 24 h ago), not already deleted, not refused (a refused one uses Descartar). Never while running.
    public func canDelete(id: String, now: Date) -> Bool {
        guard let item = items[id], item.deleted == nil, item.rejected == nil, let end = item.session.endedAt else { return false }
        return item.final == true || now.timeIntervalSince(end) > Session.editWindow
    }

    /// "Borrar sesión" (G91): one new rev, held + 1, with 0 exercises and no note (contract N9: the server copy drops
    /// its sets, the pull removes its rows). The original is kept as `deleted`. Returns the rev for the server and the
    /// Watch, nil when refused.
    public mutating func delete(id: String, now: Date) -> Session? {
        guard canDelete(id: id, now: now), var item = items[id] else { return nil }
        item.deleted = item.session
        item.session.exercises = []
        item.session.note = nil
        item.session.rev += 1
        items[id] = item
        return item.session
    }

    /// "Deshacer" / "Recuperar" (G91): the deleted session back exactly as it was, as a new rev above the emptied one.
    public mutating func restore(id: String) -> Session? {
        guard var item = items[id], var doc = item.deleted else { return nil }
        doc.rev = item.session.rev + 1
        item.session = doc
        item.deleted = nil
        item.rejected = nil
        items[id] = item
        return doc
    }

    /// Deleted sessions, newest first ("Borradas (n)").
    public var deleted: [Session] {
        items.values.compactMap(\.deleted).sorted { $0.startedAt > $1.startedAt }
    }

    /// Sessions whose latest rev has not been accepted yet and isn't parked, oldest first.
    public var pending: [Session] {
        items.values.filter { $0.session.rev > $0.sentRev && $0.rejected == nil }.map(\.session)
            .sorted { $0.startedAt < $1.startedAt }
    }

    /// Sessions the Worker refused, oldest first ("Rechazada" on the phone).
    public var rejected: [Item] {
        items.values.filter { $0.rejected != nil }.sorted { $0.session.startedAt < $1.session.startedAt }
    }

    /// Parks a refused rev so one bad session never blocks the ones after it. Kept, never dropped.
    public mutating func reject(id: String, rev: Int, error: String) {
        guard var item = items[id], item.session.rev == rev else { return }
        item.rejected = error
        items[id] = item
    }

    /// The athlete discarded this session on the Watch: never send it again.
    // lean: a copy the Worker already received stays there unfinished; the pull skips unfinished
    // sessions, so it never reaches the CSV. Add a DELETE route if those rows ever matter.
    public mutating func discard(id: String) {
        items[id] = nil
        bury(id, rev: .max) // the Watch removed its file: no later copy of it is real
    }

    private mutating func bury(_ id: String, rev: Int) {
        tombstones = (tombstones ?? [:]).merging([id: rev]) { max($0, $1) }
    }

    /// "Descartar" on a "Rechazadas" row (G51): forgets the session only while its latest rev is the refused one, and
    /// returns that rev for the Watch. A newer rev that arrived meanwhile is pending, not refused: kept, nil.
    public mutating func dismiss(id: String) -> Int? {
        guard let item = items[id], item.rejected != nil else { return nil }
        items[id] = nil
        bury(id, rev: item.session.rev) // a newer rev (an edit on the Watch) is still sent and judged again
        return item.session.rev
    }

    /// The rev to ack back to the Watch for this session: the highest the Worker accepted, if any.
    public func ackRev(id: String) -> Int? {
        items[id].flatMap { $0.sentRev > 0 ? $0.sentRev : nil }
    }

    public mutating func markSent(id: String, rev: Int) {
        guard var item = items[id] else { return }
        item.sentRev = max(item.sentRev, rev)
        items[id] = item
    }
}

extension Session {
    /// Gives back `unedited` to each set that is again exactly as in `before`. Sets pair by slot, exercise and
    /// `done_at`, in order, each once (a phone-added copy shares its source's `done_at` and comes after it).
    mutating func keepUnedited(from before: Session) {
        var pool = before.exercises.flatMap { e in e.sets.map { (e.slot, e.exerciseTemplateId, $0) } }
        for i in exercises.indices {
            for j in exercises[i].sets.indices {
                let s = exercises[i].sets[j], e = exercises[i]
                guard let k = pool.firstIndex(where: { $0.0 == e.slot && $0.1 == e.exerciseTemplateId && $0.2.doneAt == s.doneAt })
                else { continue }
                let old = pool.remove(at: k).2
                if old.unedited, old.weightKg == s.weightKg, old.reps == s.reps { exercises[i].sets[j].unedited = true }
            }
        }
    }
}
