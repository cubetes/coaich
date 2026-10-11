---
name: roadmap
description: Lay out the long-term plan: a dated macrocycle with phases (cut, bulk or maintenance), each with gates, its mesocycles and its weeks with their types, in plan/roadmap.md. Use for "plan my year", "what's the long-term plan", when a phase's gates come due, or when the monthly check-in asks to re-plan.
---

# Roadmap

One script does the dates and the gates: `${CLAUDE_PLUGIN_ROOT}/scripts/roadmap.py`. Never work out a date, a
program week or a gate band yourself; copy what it prints. Vocabulary (fixed, use it exactly):
[periodization-system.md](../../references/periodization-system.md).

Run from the athlete folder (it holds `coaich.md`). Read `plan/CURRENT.md` first: it wins over every other file.

## 1. Gate check

Call the Skill tool with `safety` unless it ran in this conversation. `safety_status: stop` → no plan is made or
changed: say so in one line (the safety skill's wording). The script refuses too (exit 2).

A program must exist (`plan/program.json`); if not, run `program-build` first.

## 2. Ask (only what is missing)

- **How long.** Default 52 weeks from the next Monday (`--start` moves it).
- **Phases.** A phase is the energy-balance direction only: `cut`, `bulk` or `maintenance`. Default: one
  maintenance phase. A cut or bulk needs the `nutrition` skill set up and its safeguards passed (18 or over, the
  eating-disorder answer "no", not paused); the script refuses otherwise and the answer is maintenance. Never
  argue a refusal. Phase names map to the nutrition skill's `nutrition_phase`: cut = lose, bulk = gain,
  maintenance = maintain.

## 3. Make

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/roadmap.py" make --dir . [--start YYYY-MM-DD] [--phases maintenance:12,bulk:24]
```

It writes `plan/roadmap.md` (header = the data, body = tables rewritten from it), a roadmap block in
`plan/CURRENT.md` and a `log.md` line. Present:

- **Phases** with dates and their **gates**, each in plain words: `sessions_per_week 3..` = "at least 3 sessions
  a week"; `hit_rate 70..85` = "you meet 70–85 % of your weekly targets"; `e1rm:<lift> 5..` = "your estimated
  best single on that lift up at least 5 %"; `weight_rate 0.1..0.5` = "body weight up 0.1–0.5 % a week". Say
  once that these are coaching bands (our rule), not study cut-offs.
- **Mesocycles**: one program block each, ending on its easy week (intermediate every 7th program week, advanced
  every 6th; beginners have none planned and change program after the 4-week ramp, then every 6 weeks).
- **Microcycles**: the projected weeks. Say plainly: easy weeks count in sessions done, so a missed session moves
  every later week; the dates are a forecast, the sessions are the truth.

## 4. Check and re-plan (the monthly check-in calls this)

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/roadmap.py" check --dir .
```

Gates are due in a phase's last 2 weeks. Show the gate table. Then the athlete picks:

| Gates | Offer | Command |
|---|---|---|
| all in band | next phase starts next Monday | `replan --outcome passed` |
| some off band | extend this phase (default 4 weeks), or move on with the miss written down | `replan --outcome missed [--extend-weeks N]` · `replan --outcome move-on` |
| no data | say what is missing (weigh-ins, logged sessions); decide as for "off band" | |

Every re-plan shifts the later phases and rewrites the tables. When a new phase starts, tell the athlete which
`nutrition_phase` the nutrition skill should now use (if nutrition is on); the nutrition skill makes that change.

`show` refreshes the tables and the CURRENT.md block without changing the plan.

## 5. Log

The script logs `make` and `replan`. Nothing else to log.

## Never

- Promise a result or a date for a body change; gates are checks, not guarantees.
- Plan calories, a diet break or a cut without the nutrition skill.
- Hand-edit the body of `plan/roadmap.md`: edit the header and run `show`, or re-plan.
