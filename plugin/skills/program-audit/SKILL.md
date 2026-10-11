---
name: program-audit
description: Check a training program against the evidence and report gates (pass or fail) and preferences (notes), each with its source. Use for "is my program good", "check my routine", or to audit a generated program after a change.
---

# Program audit

Audits any program: the one `program-build` made, or one the user wrote. Gates can fail; preferences never
fail, they are notes. Every line names its source and grade, from [evidence.md](../../references/evidence.md):
a study (SR/MA, RCT, OBS) or "our rule" (practitioner). Never call a preference a failure, and never present an
"our rule" number as a finding of science.

## 1. Get the program into program.json shape

- **Generated program** → it is already `plan/program.json`. Go to 2.
- **The user's own program** (pasted, a photo, a Hevy routine, a spreadsheet) → write it to a scratch file in the
  shape of [program-schema.md](../../docs/program-schema.md) §Hand-written programs: `level` (from `plan/program.json`, else
  `program_build.py --dir <folder> --place`; never worked out by hand), `days`, `minutes` if known, and per day the exercises with `exercise_id` and `sets`
  (`rep_range`, `reps_left` if given). Map each exercise to a free-exercise-db id
  (`${CLAUDE_PLUGIN_ROOT}/data/exercises.json`; reuse `data/exercise_map.csv`). Unsure match → ask; never guess
  silently. Add `pain` from `profile.md`. Do not overwrite `plan/program.json` with it.

## 2. Run

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/program_audit.py" --program <file>     # or --dir <folder>
```

Exit 0 passes, 1 has an unexpected gate failure, 2 the file is unusable (it says which field).

## 3. Report

Lead with the result in one line, then the gate table, then the notes. Explain each failure with what to change
and why. The gates:

| Gate | Check | Source |
|---|---|---|
| G1 | weekly effective sets per group ≥ floor (beginner 4, intermediate+ 10 for chest, back, quads, hamstrings, 4 for the rest; 3 / 6 at 30–45 min) | Schoenfeld 2017, Currier 2026 (SR/MA); short-session floors our rule |
| G2 | no group over the MRV coaching band | RP bands, P |
| G3 | every group in ≥ 2 sessions a week | Pelland 2025, Currier 2026 (SR/MA): strength, not size |
| G4 | every session within the minutes | the athlete's answer; time formula our rule |
| G5 | effort: compounds ≥ 1 in reserve, spine lifts and beginners' first 4 weeks ≥ 2 | Robinson 2024, Refalo 2023; floors our rule |
| G6 | pain: no spine loading with a low back, nothing loading a red-flag area, no flyes with a shoulder, no leg extension with a knee | our rule |
| G7 | valid ids, no exercise twice a day, ≤ 7 a day, pairs of two | our rule |
| G8 | sets per exercise ≤ 4 (beginner 3; 60+ 2 for 8 weeks) | Krieger 2010; Fragala 2019 |

Notes (never failures): G9 overhead triceps extension (Maeo 2023, one RCT) · P1 a direct rear-delt exercise
(our rule) · P2 a standing calf raise (Kinoshita 2023, small RCT) · P3 easy-week interval matches the level
(interval our rule) · P4 a heavier main lift for a strength or both goal (Moesgaard 2022: 1RM in trained lifters
only). A **known miss** is a listed exception with its reason (e.g. 2 days a week cannot reach 10 sets): report
it as a note, not a failure.

Things the script cannot see, check by reading and report as notes only when relevant: 5 or more training days
in a row without rest (our rule), exercises whose movement slot is unknown (the report lists them; check pain
by hand), and sleep under 7 hours if the user mentions it (recovery, not a program fault).

## 4. Log

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" log program-audit "<name>: passes | N failures"`.
To fix a generated program, change `profile.md` and run `program-build`; never hand-edit `plan/program.json`.
