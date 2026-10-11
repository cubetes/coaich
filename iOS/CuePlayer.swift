import AVFoundation
import AthleteCore
import os

/// Short synthesized tones in the headphones (G15). iOS won't let a backgrounded app *start* audio (G50,
/// research/2026-10-09-background-audio-cues.md), so the session stays active and the engine runs (silence) for the
/// whole workout, mixable without ducking; music ducks only around a cue cluster. Each tone is placed on the audio
/// clock at its exact `Date`, not when a timer fires.
@Observable
final class CuePlayer {
    /// The last cue attempts and audio-session events, newest first, in Spanish ("Diagnóstico de sonidos").
    private(set) var log: [String] = []
    /// Built at the first activation, never at launch: touching the engine's mixer before the category is mixable
    /// makes iOS treat the app as a non-mixing player and pause Spotify on open (G52).
    @ObservationIgnored private var engine: AVAudioEngine?
    @ObservationIgnored private let player = AVAudioPlayerNode()
    @ObservationIgnored private let format = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 1)!
    @ObservationIgnored private let audio = AVAudioSession.sharedInstance()
    @ObservationIgnored private let logger = Logger(subsystem: "athleteos", category: "cues")
    @ObservationIgnored private var holds = 0
    @ObservationIgnored private var workout = false

    init() {
        // Mixable before anything touches audio; only sets the category, never activates (G52).
        do { try audio.setCategory(.playback, options: [.mixWithOthers]) } catch { note(nil, "categoría · \(error)") }
    }

    /// A workout runs: keep the session active until `endWorkout`. Safe to call again (from the foreground it
    /// succeeds even when the background launch's try failed). False: the audio couldn't start (G53 hint).
    func startWorkout(_ why: String) -> Bool {
        workout = true
        return activate(why)
    }

    func endWorkout() {
        workout = false
        if holds == 0 { deactivate() }
    }

    /// "Probar sonido": the rest-over chime through the same path, now.
    func test() async { await play(ScheduledCue(at: .now.addingTimeInterval(0.3), cue: .restOver)) }

    /// Sleeps until just before `cue.at`, then places the tone on the audio clock. Cancelling before that
    /// plays nothing.
    func play(_ cue: ScheduledCue) async {
        do {
            try await Task.sleep(for: .seconds(max(0, cue.at.timeIntervalSinceNow - 1))) // warm-up: route + duck
        } catch { return }
        guard UserDefaults.standard.object(forKey: "cuesOn") as? Bool ?? true else { return note(cue.cue, "omitido: sonidos desactivados") }
        guard headphones() else { return note(cue.cue, "omitido: no son auriculares · \(route())") }
        guard onTime(cue), hold(cue.cue) else { return }
        do {
            try await Task.sleep(for: .seconds(max(0, cue.at.timeIntervalSinceNow - Cues.placeAhead)))
        } catch { release(); return }
        // Again at the last moment: AirPods taken out, or the app held up, since the first check.
        guard headphones() else { note(cue.cue, "omitido: no son auriculares · \(route())"); return release() }
        guard onTime(cue) else { return release() }
        if engine?.isRunning != true, !activate("reinicio", cue.cue) { return release() } // a route change stops the engine
        let buffer = Self.buffer(cue.cue, format: format)
        let delay = max(0, cue.at.timeIntervalSinceNow)
        player.scheduleBuffer(buffer, at: AVAudioTime(hostTime: mach_absolute_time() + AVAudioTime.hostTime(forSeconds: delay)),
                              options: [], completionHandler: nil)
        note(cue.cue, "reproducido · \(route())")
        let tail = delay + Double(buffer.frameLength) / format.sampleRate + 0.8
        DispatchQueue.main.asyncAfter(deadline: .now() + tail) { self.release() }
    }

    private func headphones() -> Bool { Cues.isHeadphones(audio.currentRoute.outputs.map { ($0.portType.rawValue, $0.portName) }) }

    private func route() -> String {
        let outs = audio.currentRoute.outputs.map { "\($0.portType.rawValue) “\($0.portName)”" }
        return outs.isEmpty ? "sin salida" : outs.joined(separator: ", ")
    }

    private func onTime(_ cue: ScheduledCue) -> Bool {
        let late = -cue.at.timeIntervalSinceNow
        if late > Cues.lateness { note(cue.cue, "descartado: tarde \(late.formatted(.number.precision(.fractionLength(1)))) s") }
        return late <= Cues.lateness
    }

    /// Session active (mixable, no duck) and engine running; logs the outcome. Calls `setActive(true)` again on every
    /// (re)start, so it also recovers after an interruption.
    private func activate(_ why: String, _ cue: Cue? = nil) -> Bool {
        if engine?.isRunning == true { return true }
        do {
            try step("categoría") { try audio.setCategory(.playback, options: [.mixWithOthers]) }
            try step("activar") { try audio.setActive(true) }
            let engine = self.engine ?? graph()
            try step("motor") { try engine.start() }
            try step("reproductor") { try player.playAudio() }
            note(cue, "audio listo (\(why))")
            return true
        } catch {
            note(cue, "error de audio (\(why)) · \(error)")
            return false
        }
    }

    private func graph() -> AVAudioEngine {
        let engine = AVAudioEngine()
        engine.attach(player)
        try? engine.connectNode(player, to: engine.mainMixerNode, format: format) // a failure shows up in the log as no engine start
        self.engine = engine
        return engine
    }

    /// Ducks the music around a cue cluster (G28): one dip for a rest's 5…1 + rest over.
    private func hold(_ cue: Cue) -> Bool {
        guard activate("aviso", cue) else { return false }
        if holds == 0 {
            do {
                try step("bajar música") {
                    try audio.setCategory(.playback, options: [.mixWithOthers, .duckOthers])
                    try audio.setActive(true)
                }
            } catch { note(cue, "aviso sin bajar la música · \(error)") } // the tone still plays
        }
        holds += 1
        return true
    }

    private func release() {
        holds -= 1
        guard holds == 0 else { return }
        guard workout else { return deactivate() }
        // Never deactivate mid-workout: the next cue would be a fresh start from the background (refused).
        // lean: unproven that the music un-ducks without a deactivation; if it stays low, drop .duckOthers during workouts.
        do {
            try step("subir música") {
                try audio.setCategory(.playback, options: [.mixWithOthers])
                try audio.setActive(true)
            }
        } catch { note(nil, "error de audio · \(error)") }
    }

    private func deactivate() {
        if let engine {
            player.stop()
            engine.stop()
        }
        do {
            try audio.setActive(false, options: .notifyOthersOnDeactivation) // music back to full volume
            note(nil, "audio cerrado")
        } catch { note(nil, "error al cerrar el audio · \(error)") }
    }

    /// Runs `work`, rethrowing its error tagged with the step's name, domain and code ("activar · NSOSStatusErrorDomain 561015905").
    private func step(_ name: String, _ work: () throws -> Void) throws {
        do { try work() } catch {
            let e = error as NSError
            throw StepError(text: "\(name) · \(e.domain) \(e.code)")
        }
    }

    private struct StepError: Error, CustomStringConvertible { let text: String; var description: String { text } }

    /// The lock-screen panel's start, in the same list (G108).
    func notePanel(_ outcome: String) { note(nil, outcome, what: "Panel") }

    private func note(_ cue: Cue?, _ outcome: String, what: String = "Audio") {
        let line = "\(Date.now.formatted(date: .omitted, time: .standard)) · \(cue.map(Self.name) ?? what) · \(outcome)"
        logger.notice("\(line, privacy: .public)")
        log.insert(line, at: 0)
        if log.count > 30 { log.removeLast() }
    }

    private static func name(_ cue: Cue) -> String {
        switch cue {
        case .start(let n): "Cuenta atrás \(n)"
        case .go: "¡Vamos!"
        case .restTick(let n): "Descanso \(n)"
        case .restOver: "Fin del descanso"
        case .setSaved: "Serie guardada"
        }
    }

    // MARK: Tones

    private static func buffer(_ cue: Cue, format: AVAudioFormat) -> AVAudioPCMBuffer {
        switch cue {
        case .start: tone([(880, 0.07)], gain: 0.25, format: format)
        case .go: tone([(1320, 0.22)], gain: 0.45, format: format)
        case .restTick(let n): // 5…1: higher and louder toward 0
            tone([(520 + Double(5 - n) * 90, 0.07)], gain: 0.12 + Float(5 - n) * 0.06, format: format)
        case .restOver: tone([(988, 0.12), (1319, 0.25)], gain: 0.5, format: format)
        case .setSaved: tone([(660, 0.06), (880, 0.09)], gain: 0.18, format: format)
        }
    }

    /// Sine notes back to back, each with a 5 ms attack and a fade over its last 40 % (no clicks).
    private static func tone(_ notes: [(hz: Double, seconds: Double)], gain: Float, format: AVAudioFormat) -> AVAudioPCMBuffer {
        let rate = format.sampleRate
        let total = notes.reduce(0) { $0 + Int($1.seconds * rate) }
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(total))!
        buffer.frameLength = AVAudioFrameCount(total)
        let out = buffer.floatChannelData![0]
        var i = 0
        for note in notes {
            let n = Int(note.seconds * rate)
            let attack = Int(0.005 * rate), fade = Int(Double(n) * 0.4)
            for k in 0..<n {
                let env = min(1, Float(k) / Float(attack), Float(n - k) / Float(fade))
                out[i] = gain * env * Float(sin(2 * .pi * note.hz * Double(k) / rate))
                i += 1
            }
        }
        return buffer
    }
}
