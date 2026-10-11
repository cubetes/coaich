import Foundation

/// The web app's `lib/lift.ts` rules, ported 1:1 for the iPhone's Entreno (G82, red team must-fix 4–5). They pick, order
/// and label what the snapshot published; they never compute a target, a grade or a decision. Dates are the
/// snapshot's "YYYY-MM-DD" strings (local calendar days).
public enum Lift {
    // MARK: Numbers and dates

    /// "107,5" · "8,75" · "100": decimal comma, no thousands separator, at most 2 decimals (the web's `fmtNum`);
    /// `digits` fixes the decimals.
    public static func num(_ v: Double, digits: Int? = nil) -> String {
        guard v.isFinite else { return "—" }
        let style = FloatingPointFormatStyle<Double>.number.locale(Locale(identifier: "es_ES")).grouping(.never)
            .rounded(rule: .toNearestOrAwayFromZero)
        let out = digits.map { v.formatted(style.precision(.fractionLength($0))) } ?? v.formatted(style.precision(.fractionLength(0...2)))
        return out.hasPrefix("-") && Double(out.dropFirst().replacingOccurrences(of: ",", with: ".")) == 0 ? String(out.dropFirst()) : out
    }

    static let months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    static let weekdaysShort = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"] // Monday first
    static let initials = ["L", "M", "X", "J", "V", "S", "D"]

    /// (year, month, day) of "YYYY-MM-DD", or nil.
    static func parts(_ ymd: String) -> (Int, Int, Int)? {
        let p = ymd.prefix(10).split(separator: "-").compactMap { Int($0) }
        guard ymd.count >= 10, p.count == 3, (1...12).contains(p[1]), (1...31).contains(p[2]) else { return nil }
        return (p[0], p[1], p[2])
    }

    /// Pure calendar arithmetic (UTC, no time zone can shift a day).
    private static var utc: Calendar {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "UTC")!
        return c
    }

    private static func date(_ ymd: String) -> Date? {
        guard let (y, m, d) = parts(ymd) else { return nil }
        return utc.date(from: DateComponents(year: y, month: m, day: d))
    }

    private static func ymd(_ date: Date) -> String {
        let c = utc.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", c.year!, c.month!, c.day!)
    }

    public static func addDays(_ ymd: String, _ n: Int) -> String {
        guard let d = date(ymd), let out = utc.date(byAdding: .day, value: n, to: d) else { return ymd }
        return Self.ymd(out)
    }

    /// 0 = Monday … 6 = Sunday.
    public static func weekdayMon0(_ ymd: String) -> Int {
        guard let d = date(ymd) else { return 0 }
        return (utc.component(.weekday, from: d) + 5) % 7
    }

    public static func mondayOf(_ ymd: String) -> String { addDays(ymd, -weekdayMon0(ymd)) }

    /// Whole days from `a` to `b`.
    static func days(from a: String, to b: String) -> Int? {
        guard let x = date(a), let y = date(b) else { return nil }
        return utc.dateComponents([.day], from: x, to: y).day
    }

    /// "21 sep".
    public static func short(_ ymd: String) -> String {
        guard let (_, m, d) = parts(ymd) else { return ymd }
        return "\(d) \(months[m - 1])"
    }

    /// "Sáb 10 oct".
    public static func dayLabel(_ ymd: String) -> String { "\(weekdaysShort[weekdayMon0(ymd)]) \(short(ymd))" }

    /// "5–11 oct" or "28 sep – 4 oct" for the week starting on Monday `monday`.
    public static func weekRange(_ monday: String) -> String {
        let (a, b) = (short(monday), short(addDays(monday, 6)))
        let (am, bm) = (a.split(separator: " ").last, b.split(separator: " ").last)
        return am == bm ? "\(a.split(separator: " ")[0])–\(b)" : "\(a) – \(b)"
    }

    // MARK: Freshness (web `isStale` 9 days, `isLiftStale`, `LiftFreshness`)

    /// The snapshot is older than `days` (web `isStale`: now − local midnight of `as_of_date`).
    public static func isStale(asOf: String?, now: Date, days: Int = 9) -> Bool {
        guard let asOf, let (y, m, d) = parts(asOf),
              let midnight = Calendar.current.date(from: DateComponents(year: y, month: m, day: d)) else { return false }
        return now.timeIntervalSince(midnight) > Double(days) * 86_400
    }

    /// Neither the newest session nor the last pull is from this week (FR-009): the objectives may be last week's. A
    /// Monday pull after a Sunday session is fresh.
    public static func isLiftStale(_ meta: Entreno.Meta, today: String) -> Bool {
        guard let d = meta.dataThrough, parts(d) != nil else { return true }
        let pulled = meta.syncedAt.flatMap { try? Date($0, strategy: .iso8601) }.map { Plan.day($0) } ?? ""
        let monday = mondayOf(today)
        return d < monday && pulled < monday
    }

    /// How the last refresh went: `ok`, no answer (`offline`: no network or a server error), or an answer the phone
    /// couldn't use (`unreadable`, `unsupported` = a newer schema major). Anything but `ok` keeps the last good plan.
    public enum Refresh: Sendable { case ok, offline, unreadable, unsupported }

    /// At most one freshness line on Entreno (owner 2026-10-05; red team EN-12), by priority: the refresh failed →
    /// the snapshot is > 9 days old → no session/pull this week → this week's objectives weren't reviewed. nil = fresh.
    /// `lastSync` (when the phone asked) is never freshness.
    public static func freshness(asOf: String?, meta: Entreno.Meta?, refresh: Refresh, now: Date,
                                 today: String = Plan.day()) -> String? {
        let date = asOf.map { "Datos al \(short($0))" } ?? "Datos sin fecha"
        switch refresh { // never "Sin conexión" for a body it couldn't read (EN-29)
        case .ok: break
        case .offline: return "Sin conexión · \(date)"
        case .unreadable: return "No se pudo leer el plan nuevo · \(date)"
        case .unsupported: return "Hay un plan nuevo para una versión más reciente: actualiza la app · \(date)"
        }
        if isStale(asOf: asOf, now: now) { return "\(date) · puede no reflejar lo más reciente" }
        guard let meta else { return nil }
        if isLiftStale(meta, today: today) {
            let synced = meta.dataThrough.map { "Entrenos sincronizados hasta el \(short($0))" } ?? "Sin entrenos sincronizados"
            return "\(synced) · los objetivos pueden ser de la semana pasada"
        }
        switch meta.targetsStatus {
        case "unreviewed": return "Objetivos sin revisar esta semana: son los de la semana pasada"
        case "none": return "Sin objetivos esta semana"
        default: return nil
        }
    }

    // MARK: Labels

    /// Last week's mark: ✓ Cumplido · "Parcial" (a word, never "½") · ✗ No cumplido (caution, never red) · — Sin datos.
    public enum Grade: String, Sendable {
        case hit, partial, miss, none
        public init(_ published: String?) { self = Grade(rawValue: published ?? "") ?? .none }
        public var glyph: String { [.hit: "✓", .partial: "Parcial", .miss: "✗"][self] ?? "—" }
        public var label: String { [.hit: "Cumplido", .partial: "Parcial", .miss: "No cumplido"][self] ?? "Sin datos" }
    }

    public static let decision = ["increase": "Sube", "hold": "Mantén", "reduce": "Baja", "deload": "Descarga", "swap": "Cambio"]

    /// "8-10" → "8–10".
    public static func reps(_ r: String) -> String {
        r.replacingOccurrences(of: #"(\d)\s*-\s*(\d)"#, with: "$1–$2", options: .regularExpression)
    }

    /// "3:00" from seconds; nil when absent or ≤ 0.
    public static func rest(_ s: Int?) -> String? {
        guard let s, s > 0 else { return nil }
        return "\(s / 60):\(s % 60 < 10 ? "0" : "")\(s % 60)"
    }

    /// The objective as published: "107,5 kg × 8·8·8·8"; `compact` folds equal sets ("107,5 kg × 8").
    public static func objective(_ target: Entreno.Slot.Target?, compact: Bool = false) -> String? {
        guard let t = target else { return nil }
        let r = t.reps.split(separator: "·").map { $0.trimmingCharacters(in: .whitespaces) }
        let shown = compact && r.count > 1 && r.allSatisfy { $0 == r[0] } ? r[0] : t.reps
        return "\(num(t.kg)) kg × \(reps(shown))"
    }

    public enum Status: String, Sendable { case pending, rejected, auto, unreviewed }

    /// Which objective caption applies. Pending wins (the held objective shows); a rejected proposal shows the held
    /// objective with a neutral "No aceptado".
    public static func status(_ target: Entreno.Slot.Target?, targets: String?) -> Status? {
        guard let t = target else { return nil }
        if t.approval == "pending" { return .pending }
        if t.approval == "rejected" { return .rejected }
        if t.source == "auto" { return .auto }
        if t.source == "held" || targets == "unreviewed" { return .unreviewed }
        return nil
    }

    public static func label(_ s: Status) -> String {
        switch s {
        case .pending: "Esperando tu OK al coach"
        case .rejected: "No aceptado"
        case .auto: "Actualizado automáticamente"
        case .unreviewed: "Sin revisar esta semana"
        }
    }

    /// The change tag — only a real change (the plugin's words, else Sube/Baja/Descarga/Cambio). Nothing for a hold
    /// (even if `change_es` says "↑ …"), a rejected, pending or unreviewed objective.
    public static func changeWord(_ target: Entreno.Slot.Target?, status: Status?) -> String? {
        guard let t = target, t.decision != "hold" else { return nil }
        if status == .pending || status == .unreviewed || status == .rejected { return nil }
        return t.changeEs ?? t.decision.flatMap { decision[$0] }
    }

    /// "Baja en 3 s. Pausa breve abajo." → ["Baja en 3 s.", "Pausa breve abajo."] (max 3).
    public static func cueBullets(_ cue: String?) -> [String] {
        guard let cue else { return [] }
        var out: [String] = [], cur = ""
        for ch in cue {
            cur.append(ch)
            if ch == "." { out.append(cur); cur = "" }
        }
        out.append(cur)
        return Array(out.map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty && $0 != "." }.prefix(3))
    }

    /// The last time, from the published `history[0]` with its date, never from this phone's sessions (EN-14):
    /// "Últ. 105 × 10 · 21 sep"; "Primera vez" only when there is none and last week has no mark. A graded slot was
    /// done before (its history trimmed by the publisher's size governor): nil, never "Primera vez" beside a ✓.
    public static func last(_ history: [Entreno.Slot.History]?, grade: String? = nil) -> String? {
        guard let h = history?.first else { return Grade(grade) == .none ? "Primera vez" : nil }
        return "Últ. \(top(h.top))" + (h.date.map { " · \(short($0))" } ?? "")
    }

    /// "Objetivo 111,5 kg × 8 · Últ. 111,5 × 8 (26 sep)" under the guide's title (G84).
    public static func objectiveLine(_ slot: Entreno.Slot) -> String {
        let o = objective(slot.target, compact: true).map { "Objetivo \($0)" } ?? "Sin objetivo"
        guard let h = slot.history?.first else { return Grade(slot.lastWeek?.grade) == .none ? "\(o) · Primera vez" : o }
        return "\(o) · Últ. \(top(h.top))" + (h.date.map { " (\(short($0)))" } ?? "")
    }

    /// "105×10" → "105 × 10".
    static func top(_ s: String) -> String {
        s.replacingOccurrences(of: #"\s*×\s*"#, with: " × ", options: .regularExpression)
    }

    // MARK: Week strip

    /// Short routine initials, unique in `order`: "Push A" → "PA", then "Pull A" → "PuA".
    public static func routineInitials(_ routines: [String: Entreno.Routine], order: [String]) -> [String: String] {
        var out: [String: String] = [:], taken = Set<String>()
        for key in order {
            guard let r = routines[key] else { continue }
            let words = r.title.split(whereSeparator: \.isWhitespace).map(String.init)
            let rest = words.dropFirst().compactMap { $0.first?.uppercased() }.joined()
            let first = words.first ?? "?"
            var label = ""
            for n in 1...max(1, first.count) {
                let head = first.prefix(n)
                label = head.prefix(1).uppercased() + head.dropFirst().lowercased() + rest
                if !taken.contains(label) { break }
            }
            taken.insert(label)
            out[key] = label
        }
        return out
    }

    public struct DayCell: Equatable, Sendable {
        public let date: String
        public let initial: String
        public let dayNum: Int
        public let label: String
        public let state: String
        public let isToday: Bool
        public let title: String?
    }

    public static func weekCells(_ e: Entreno, order: [String], today: String) -> [DayCell] {
        let names = routineInitials(e.routines ?? [:], order: order)
        return (e.week ?? []).sorted { $0.date < $1.date }.map { d in
            DayCell(date: d.date, initial: initials[weekdayMon0(d.date)], dayNum: parts(d.date)?.2 ?? 0,
                    label: d.routineKey.flatMap { names[$0] ?? d.title } ?? "—", state: d.state ?? "planned",
                    isToday: d.date == today, title: d.title)
        }
    }

    /// The day's state spoken: "hecho" · "planificado" · "saltado" · "descanso".
    public static func dayState(_ s: String) -> String {
        ["done": "hecho", "planned": "planificado", "skipped": "saltado", "rest": "descanso"][s] ?? s
    }

    // MARK: Trend (display only)

    public static let trendMinSessions = 8
    public static let trendMinWeeks = 6

    /// "+5,7 %" · "−3,4 %" · "0 %".
    public static func pct(_ v: Double) -> String {
        let r = (v * 10).rounded() / 10
        if r == 0 { return "0 %" }
        return "\(r > 0 ? "+" : "−")\(num(abs(r), digits: r == r.rounded() ? 0 : 1)) %"
    }

    public static func calibrating(_ t: Entreno.Trend) -> String {
        "Aún sin tendencia · \(t.sessions ?? 0) de \(trendMinSessions) sesiones"
    }

    /// The chip: the verdict when ok ("sube +5,7 %"), else "Calibrando n/8".
    public static func trendChip(_ t: Entreno.Trend?) -> String? {
        guard let t else { return nil }
        guard t.status == "ok", let v = t.verdict else {
            return "Calibrando \(min(t.sessions ?? 0, trendMinSessions))/\(trendMinSessions)"
        }
        return v + (t.deltaPct.map { " \(pct($0))" } ?? "")
    }

    // MARK: Live rows (EN-18)

    public struct LiveRow: Equatable, Sendable {
        public let done: Int
        public let planned: Int
        public let isCurrent: Bool
        /// "2/4 · ahora" · "3/3 ✓" · "0/3".
        public var text: String {
            "\(done)/\(planned)" + (isCurrent ? " · ahora" : done >= planned && planned > 0 ? " ✓" : "")
        }
    }

    /// Per-row counts by slot key, only when the Watch sent its keys for this routine and they line up with its
    /// segments; nil otherwise (then only the hero shows progress, never counts by index against another plan).
    public static func liveRows(_ state: LiveState, routineKey: String) -> [String: LiveRow]? {
        guard state.routineKey == routineKey, let slots = state.slots, let segs = state.segments,
              slots.count == segs.count else { return nil }
        var out: [String: LiveRow] = [:]
        for (i, key) in slots.enumerated() {
            out[key] = LiveRow(done: segs[i].done, planned: segs[i].planned, isCurrent: state.current == i)
        }
        return out
    }

    /// The routine Rutina lists (test 18, G100 c): a picked day shows that day's plan; today shows the routine running on
    /// the Watch first — not the suggestion, else a session started on the Watch with another routine never gets rows.
    public static func shownRoutine(day: String?, week: [Entreno.Day]?, liveKey: String?, picked: String?,
                                    suggested: String?) -> String? {
        if let day { return week?.first { $0.date == day }?.routineKey }
        return liveKey ?? picked ?? suggested
    }

    // MARK: Start on the Watch (G100)

    /// The Watch link for the start button and Ajustes, judged by evidence (G107): `reachable`, or anything heard from
    /// the Watch app within `heardRecently` (a message, a session, an ack, a mirrored session or live state), wins over
    /// `isWatchAppInstalled`, which free-team installs make drop to false while transfers still work (G44/G100).
    public enum WatchLink: Equatable, Sendable {
        case ready, notActivated, notPaired, appMissing

        public static let heardRecently: TimeInterval = 15 * 60

        /// `heardAgo`: seconds since the phone last heard from the Watch app; nil = not since launch.
        public init(activated: Bool, paired: Bool, appInstalled: Bool, reachable: Bool, heardAgo: TimeInterval? = nil) {
            let heard = heardAgo.map { $0 < Self.heardRecently } ?? false
            self = reachable || (activated && heard) ? .ready
                : !activated ? .notActivated : !paired ? .notPaired : !appInstalled ? .appMissing : .ready
        }

        /// The line under a muted start button, with the fix; nil when the start should work.
        public var problem: String? {
            switch self {
            case .ready: nil
            case .notActivated: "El iPhone aún no ha conectado con el reloj. Espera unos segundos o usa «Reiniciar conexión» en Ajustes."
            case .notPaired: "No hay ningún reloj enlazado con este iPhone."
            case .appMissing: "El iPhone no ve la app del reloj. Ábrela en el reloj y vuelve a probar; si sigue, reinstala las dos apps juntas desde el Mac."
            }
        }
    }

    /// How a start from the phone ended: only the Watch's mirrored session counts as started (`startWatchApp`
    /// succeeding only means iOS passed the request on, G100 a).
    public enum StartReply: Equatable, Sendable {
        case confirmed, noReply, failed(String)

        public var text: String {
            switch self {
            case .confirmed: "Empezado en el reloj ✓"
            case .noReply: "El reloj no ha respondido. Mira el reloj: si no ha empezado, abre la app allí y empieza desde el reloj."
            case .failed(let why): "No se pudo abrir el reloj: \(why)"
            }
        }
        public var ok: Bool { self == .confirmed }
    }

    // MARK: Swipe to delete (G101 c)

    /// Where a row's horizontal swipe settles when the finger lifts: `offset` is the drag (negative = left), `width`
    /// the row's. Past half the row = delete (asks first); past half the button = the "Borrar" button stays open.
    public enum SwipeEnd: Equatable, Sendable {
        case closed, open, delete

        public static let button = 88.0

        public init(offset: Double, width: Double) {
            self = offset <= -width / 2 ? .delete : offset <= -Self.button / 2 ? .open : .closed
        }
    }

    // MARK: Sessions (this phone's outbox)

    public struct SessionWeek: Equatable, Sendable {
        public let monday: String
        /// "Semana 6 · 5–11 oct" (plan week from the phase start) or "5–11 oct".
        public let title: String
        public let sessions: [Session]
    }

    /// Finished sessions of the last `weeks` weeks, newest first, grouped by week (Monday–Sunday). The week number
    /// counts from the phase's start (`payload.plan.phase_start`) when known.
    public static func sessionWeeks(_ sessions: [Session], phaseStart: String?, now: Date, weeks: Int = 8) -> [SessionWeek] {
        let since = now.addingTimeInterval(-Double(weeks) * 7 * 86_400)
        let done = sessions.filter { $0.endedAt != nil && $0.startedAt >= since }.sorted { $0.startedAt > $1.startedAt }
        var out: [SessionWeek] = []
        for s in done {
            let monday = mondayOf(Plan.day(s.startedAt))
            if out.last?.monday == monday {
                let w = out.removeLast()
                out.append(SessionWeek(monday: monday, title: w.title, sessions: w.sessions + [s]))
            } else {
                let n = phaseStart.flatMap { days(from: mondayOf($0), to: monday) }.flatMap { $0 >= 0 ? $0 / 7 + 1 : nil }
                out.append(SessionWeek(monday: monday, title: (n.map { "Semana \($0) · " } ?? "") + weekRange(monday), sessions: [s]))
            }
        }
        return out
    }

    /// Slots where an exercise was swapped (G69): "⇄ 1 ejercicio cambiado".
    public static func swapTag(_ s: Session) -> String? {
        let n = Set(s.exercises.filter(\.substituted).map(\.slot)).count
        return n == 0 ? nil : "⇄ \(n) \(n == 1 ? "ejercicio cambiado" : "ejercicios cambiados")"
    }

    /// The end of the 24 h edit window in words: "hoy 08:23" / "mañana 08:23" (G70).
    public static func editableUntil(end: Date, now: Date, calendar: Calendar = .current) -> String {
        let until = end.addingTimeInterval(Session.editWindow)
        let day = calendar.isDate(until, inSameDayAs: now) ? "hoy" : "mañana"
        let f = Date.FormatStyle(date: .omitted, time: .shortened, locale: Locale(identifier: "es_ES"), calendar: calendar,
                                 timeZone: calendar.timeZone)
        return "\(day) \(until.formatted(f))"
    }
}

extension Outbox {
    /// The settings button's red dot (EN-08): refused sessions plus sessions still unsent an hour after their last set.
    public func problems(now: Date) -> Int {
        rejected.count + pending.filter { now.timeIntervalSince($0.endedAt ?? $0.lastActivity) > 3600 }.count
    }
}
