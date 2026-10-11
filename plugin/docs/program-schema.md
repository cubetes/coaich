# plan/program.json — schema (coaich.program/0.1)

Written by `scripts/program_build.py`; read by `program_audit.py` and the progression engine. One program per
athlete folder; `plan/CURRENT.md` says which one is in force. Exercises are free-exercise-db ids
(`data/exercises.json`); there are no vendor ids. Weights are kg.

## Top level

| Field | Type | Meaning |
|---|---|---|
| `schema` | `"coaich.program/0.1"` | |
| `start` | date | the day the program was issued (program week 1 starts here) |
| `name` | text | layout · time variant · modifiers, e.g. `ul4i·60·strength·pain` (the audit's known-miss key) |
| `layout` | `fb2b fb3b ul4b fb2i fb3i ul4i ulf5i ppl6i` | `b` = beginner tables, `i` = intermediate (advanced uses them too) |
| `level` | `beginner intermediate advanced` | caps the load jump; picks the floors and the easy-week interval |
| `goal` | `strength muscle both` or null | null for beginners |
| `days` | 2–6 | sessions a week the program really runs (may be fewer than asked: see `notes`) |
| `minutes` | 30–75 | the time answer; every routine's `minutes` is ≤ it |
| `variant` | 30 · 45 · 60 · 75 | the time version used |
| `week` | int | the program week the prescription was built for (counted in sessions done) |
| `rebuild_at_week` | int or null | rebuild with `program_build.py --week N` then (beginner ramp ends at 5, 60+ rules at 9) |
| `older` | bool | 60+ rules |
| `priority` | region or null | advanced only |
| `pain` | `[{area, red_flag, checked}]` | the areas the program was adapted to |
| `left_out` | slot codes | slots dropped for pain |
| `easy_week_every` | 7 · 6 · null | intermediate · advanced · beginner (triggered only) |
| `easy_weeks` | ints | 1-based program weeks that are easy weeks, up to week 52 |
| `placement` | object | `{level, returning, promotion_check_week, advanced_check_week, row}` |
| `notes`, `warnings` | text lists | shown beside the program (warnings are medical copy, lawyer review pending) |
| `rules_fired` | text list | the rule ids that fired (`references/starter-programs.md` §Rules) |
| `swaps` | `[{routine, from, to, why}]` | every exercise changed from the template, with the reason |
| `routines` | list | in the order they are run (sessions run in order, never by weekday) |

## routines[]

| Field | Type | Meaning |
|---|---|---|
| `order` | int | 1-based position in the rotation |
| `key` | slug | stable per program (`upper-a`); sessions match routines by `title` |
| `title` | text | `Upper A`, `Lower B`, `Push A`, `Day 1`, `Full body`, `Priority` … |
| `minutes` | number | estimate: 8 min warm-up + 3.25 min per compound set + 2 min per isolation or paired set |
| `exercises` | list | in the order they are done |

## routines[].exercises[]

| Field | Type | Meaning |
|---|---|---|
| `key` | `routine-key/exercise-slug` | stable slot id |
| `exercise_id` | free-exercise-db id | always written |
| `name`, `equipment` | text | from the catalogue |
| `pattern` | slot code | `SQ SM HI LU KE KF HP VP FL HR VR LR RD CU TE CA CO` (starter-programs.md §Slots) |
| `category` | `spine compound isolation` | spine = the spine set (load increases need the athlete's OK) |
| `tool` | `barbell_lower barbell_upper dumbbell machine bodyweight` | cables count as `machine` |
| `load_step_kg` | number | 2.5 · 2.5 · 2 · 5 · 0 by tool (the engine refines: 5 kg on lower barbells from 60 kg, learned machine steps) |
| `sets` | int | working sets |
| `rep_range` | `[lo, hi]` | double-progression range |
| `reps_left` | `[lo, hi]` | target reps in reserve on working sets |
| `rest_seconds` | int | 60 between the halves of a pair |
| `alternatives` | ids | same slot, allowed for the athlete's pain; empty after a pain swap |
| `warmup` | bool | the ramp (50 % × 8, 75 % × 4) before the first compound of the day |
| `pair` | int or null | antagonist pair number within the day |
| `main` | bool | the day's main lift (intermediate and advanced) |
| `top_set` | bool | advanced: set 1 is a top set, the rest back-offs |

## Hand-written programs

`program_audit.py` also audits a program the athlete wrote. Required: `level`, `days`, `routines[].exercises[]`
with `exercise_id` and `sets`. Optional with defaults: `minutes` (G4 skipped), `week` (steady weeks), `older`,
`pain`, `pattern` (from the slot column, else the catalogue's mechanic), `reps_left` (spine `[2,2]`, compound
`[1,2]`, isolation `[0,2]`), `alternatives`.
