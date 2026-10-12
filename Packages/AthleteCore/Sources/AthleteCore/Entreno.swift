import Foundation

/// The snapshot as the iPhone's Entreno screens read it (G82, red team EN-29): a second, phone-only decode of the same
/// `GET /api/snapshot/latest` body. `Plan` (the document sent to the Watch) never grows: the coach's words, grades,
/// guide and trends live here. Every field is optional, so a publisher that drops one never blocks anything; decode with
/// `Plan.decoder` (snake_case). The app only shows these values — it never recomputes a target, grade or decision.
public struct EntrenoSnapshot: Decodable, Sendable, Equatable {
    public let schemaVersion: String
    public let asOfDate: String?
    public let publishedAt: String?
    public let payload: Payload

    public struct Payload: Decodable, Sendable, Equatable {
        public let workout: Entreno?
        public let plan: PlanInfo?
    }

    /// `payload.plan`: only the phase start, to number the plan weeks in Sesiones.
    public struct PlanInfo: Decodable, Sendable, Equatable {
        public let phaseStart: String?
    }

    /// The schema major this app reads (the web's `SUPPORTED_MAJOR`).
    public static let supportedMajor = 1

    /// The body's `schema_version`, read on its own before the body: a newer major whose shape changed still asks for
    /// an update instead of reading as a broken snapshot. nil = not a snapshot.
    public static func schemaVersion(of data: Data) -> String? {
        struct Version: Decodable { let schemaVersion: String }
        return try? Plan.decoder.decode(Version.self, from: data).schemaVersion
    }

    /// "1.11" → true; a newer major (or garbage) → false: the app asks to be updated instead of guessing.
    public static func isSupported(_ schemaVersion: String) -> Bool {
        Int(schemaVersion.split(separator: ".").first ?? "") == supportedMajor
    }
}

/// `payload.workout` for the phone (snapshot 1.4+ "Lift" fields).
public struct Entreno: Decodable, Sendable, Equatable {
    public let meta: Meta?
    public let week: [Day]?
    public let routines: [String: Routine]?
    public let slots: [String: Slot]?
    public let guide: [String: Guide]?

    public struct Meta: Decodable, Sendable, Equatable {
        /// Newest training session in the published data (YYYY-MM-DD).
        public let dataThrough: String?
        /// When the publisher last pulled the sessions (ISO date-time).
        public let syncedAt: String?
        public let isoWeek: String?
        /// "reviewed" · "unreviewed" · "none".
        public let targetsStatus: String?
        public init(dataThrough: String?, syncedAt: String?, isoWeek: String? = nil, targetsStatus: String?) {
            self.dataThrough = dataThrough; self.syncedAt = syncedAt; self.isoWeek = isoWeek; self.targetsStatus = targetsStatus
        }
    }

    public struct Day: Decodable, Sendable, Equatable {
        public let date: String
        public let routineKey: String?
        public let title: String?
        /// "done" · "planned" · "skipped" · "rest" — as published at the last pull, never changed on the phone (EN-15).
        public let state: String?
    }

    public struct Routine: Decodable, Sendable, Equatable {
        public let title: String
        public let notesEs: String?
        public let slots: [String]
    }

    public struct Slot: Decodable, Sendable, Equatable {
        public let slug: String?
        public let name: String
        public let priority: Bool?
        /// More "weight" = more help: never compared (the plugin owns its meaning).
        public let assisted: Bool?
        public let prescription: Prescription?
        public let cueEs: String?
        public let target: Target?
        public let lastWeek: LastWeek?
        public let flags: [String]?
        /// Top set of recent sessions, newest first.
        public let history: [History]?
        /// This slot's own trend (one routine × exercise, one rep range): never merged with another routine's.
        public let trend: Trend?
        public let superset: Plan.Slot.Superset?

        public struct Prescription: Decodable, Sendable, Equatable {
            public let sets: Int?
            public let repRange: String?
            public let restS: Int?
        }

        public struct Target: Decodable, Sendable, Equatable {
            public let kg: Double
            public let reps: String
            /// "increase" · "hold" · "reduce" · "deload" · "swap".
            public let decision: String?
            public let changeEs: String?
            /// "approved" · "pending" · "rejected" · "not_needed".
            public let approval: String?
            /// "review" · "auto" · "held".
            public let source: String?
            public init(kg: Double, reps: String, decision: String?, changeEs: String?, approval: String?, source: String?) {
                self.kg = kg; self.reps = reps; self.decision = decision; self.changeEs = changeEs
                self.approval = approval; self.source = source
            }
        }

        public struct LastWeek: Decodable, Sendable, Equatable {
            /// "hit" · "partial" · "miss" · "not_done" · "excluded".
            public let grade: String?
        }

        public struct History: Decodable, Sendable, Equatable {
            public let date: String?
            /// "105×10".
            public let top: String
            public init(date: String?, top: String) { self.date = date; self.top = top }
        }
    }

    public struct Trend: Decodable, Sendable, Equatable {
        /// "calibrando" · "ok".
        public let status: String?
        /// "e1rm" · "load_at_floor".
        public let metric: String?
        public let points: [Point]?
        public let bandPct: Double?
        public let deltaPct: Double?
        /// "sube" · "estable" · "baja" (only when ok).
        public let verdict: String?
        public let sessions: Int?
        public let weeks: Int?

        public struct Point: Decodable, Sendable, Equatable {
            public let date: String
            public let value: Double
        }

        public init(status: String?, metric: String?, points: [Point]?, bandPct: Double?, deltaPct: Double?,
                    verdict: String?, sessions: Int?, weeks: Int?) {
            self.status = status; self.metric = metric; self.points = points; self.bandPct = bandPct
            self.deltaPct = deltaPct; self.verdict = verdict; self.sessions = sessions; self.weeks = weeks
        }
    }

    /// The exercise guide, by exercise slug. Every field optional.
    public struct Guide: Decodable, Sendable, Equatable {
        public let nameEs: String?
        public let whyInPlanEs: String?
        public let stepsEs: [String]?
        public let muscles: Muscles?
        public let mistakesEs: [String]?
        public let setupEs: String?
        /// Private cues (only in the authenticated snapshot; never sent to the Watch).
        public let personalEs: [String]?
        /// Start/end photos. Absent when the photo shows another machine: then no photo, even if one is bundled (EN-20).
        public let images: Images?

        public struct Muscles: Decodable, Sendable, Equatable {
            public let primary: [String]?
            public let secondary: [String]?
        }

        public struct Images: Decodable, Sendable, Equatable {
            /// Same-origin web paths, e.g. "/exercise-img/curl-barra/start.webp".
            public let start: String
            public let end: String
        }
    }
}
