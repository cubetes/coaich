# The athlete folder — data contract (v0.2)

Every CoAIch skill reads and writes one folder per athlete, wherever the user keeps it. Skills find it from the
working directory (the folder that holds `coaich.md`). Nothing leaves this folder except through the user's own
Claude session and the integrations the user turns on (Hevy MCP, Apple Health MCP, PubMed).

```
my-training/
  coaich.md              settings: language (en|es), units (kg|lb), data sources, safety acknowledgement + clearance (date, sentence)
  profile.md             intake answers (YAML header + notes)
  plan/CURRENT.md        what is in force today; wins over every other file
  plan/roadmap.md        macrocycle › phase › mesocycle › microcycle (vocabulary: references/periodization-system.md)
  plan/program.json      routine spec (no vendor ids; exercises by free-exercise-db id): program-schema.md
  plan/targets/          targets_YYYY-Www.json, one per ISO week
  plan/changes.md        dated plan changes, each with its success band
  plan/nutrition.md      targets + a day of meals, written by scripts/nutrition.py (v0.2)
  data/sets.csv          one row per set (schema below)
  data/sessions.csv      one row per session (schema below)
  data/body.csv          body measurements (schema below)
  data/health.csv        daily wearable metrics, long format (schema below)
  data/exercise_map.csv  source exercise name → exercise_id (the fix-up list)
  data/raw/              untouched exports (git-ignored)
  photos/YYYY-MM-DD/     front.jpg, side.jpg, back.jpg: face removed, metadata stripped (v0.2, git-ignored)
  photos/ratings.md      muscle-group ratings + body-fat ranges per photo date (v0.2)
  check-ins/             YYYY-MM-DD-weekly.md, YYYY-MM-DD-monthly.md
  log.md                 one line per skill run (format below)
```

All weights are stored in **kg** (lb converted on import, `coaich.md` sets the display unit). Dates are ISO 8601,
local time, `datetime` = `YYYY-MM-DDTHH:MM`. CSV: UTF-8, comma, header row, no index column. Importers are
**idempotent**: re-importing the same export never duplicates rows. Keys:

| File | Key |
|---|---|
| `sets.csv` | `session_id` + `exercise` + `set_index` (`set_index` restarts for each exercise) |
| `sessions.csv` | `session_id` |
| `health.csv` | `date` + `metric` |
| `body.csv` | `date` + `source` |
| `exercise_map.csv` | `exercise` |

Training imports replace **whole sessions**: a session in the import replaces every stored session with the same
`session_id`, or with the same start minute + `workout_name` (one workout seen through two exports), sets
included. A hand-filled `gym` survives. `scripts/athlete_folder.py` does every CSV read and write and the log line
(`read_rows`, `upsert_rows`, `replace_sessions`, `append_log`).

## data/sets.csv

| column | type | notes |
|---|---|---|
| date | YYYY-MM-DD | session date |
| datetime | YYYY-MM-DDTHH:MM | session start |
| session_id | text | stable per source session (`strong:<hash>`, `hevy:<id>`, `manual:<uuid>`) |
| workout_name | text | routine title |
| exercise | text | name as logged |
| exercise_id | text | free-exercise-db id, or `custom:<slug>` until mapped |
| set_index | int | 0-based within the exercise in this session |
| set_type | warmup\|normal\|failure\|dropset | |
| weight_kg | number | 0 for bodyweight |
| reps | int | |
| rir | int 0–5 or blank | reps left; if only RPE is known, rir = 10 − rpe (rounded, 0–5) |
| rpe | number or blank | as logged |
| seconds | int or blank | timed sets |
| distance_m | number or blank | |
| source | strong\|hevy\|manual\|app | |
| note | text or blank | |

## data/sessions.csv

`date, datetime, session_id, workout_name, duration_min, n_exercises, n_working_sets, total_volume_kg, gym, source, note`
(`gym` optional slug; `total_volume_kg` = Σ weight_kg × reps over working sets).

## data/body.csv

`date, weight_kg, waist_cm, body_fat_pct, source` (blank when unknown; `body_fat_pct` from a scale or a photo
estimate range midpoint). `source` = `scale` | `apple-health` | `photo-range` | `manual`. **One row per date and
source** (v0.2; v0.1 keyed by date only): readings from different methods are never mixed in one row, so a scale
weigh-in and a photo body-fat range on the same day both stay. An Apple Health import fills only its own
`apple-health` rows. Where one number per date is needed (weight trend, body fat, waist), `athlete_folder.body_series`
picks by source: `manual`, then `scale`, then `apple-health`, then `photo-range` (which only ever holds body fat).

## data/health.csv (long format)

`date, metric, value, unit, source` — metrics: `steps`, `sleep_h`, `hrv_ms`, `resting_hr_bpm`, `active_kcal`,
`vo2max`, `weight_kg` (weight also lands in body.csv). Source: `apple-health`.

## photos/ (v0.2, physique skill)

Only when the shared wellbeing gate is open (below: 18 or over, `eating_disorder_history: no`, no
`wellbeing_pause`) and `photos_opt_in: yes`; `scripts/photos.py` refuses every write otherwise. `photos/YYYY-MM-DD/` holds one file per pose, `front`, `side`
and `back` (`.jpg`), dated by the day they were taken. The whole `photos/` folder is git-ignored by the template.

**Face removal, before Claude sees a photo.** `photos.py file` never copies the original in. On the user's computer
it finds the face (macOS: Apple Vision face rectangles + body pose, through `scripts/anonymise.swift`, compiled once
into `~/Library/Caches/coaich/`; Windows/Linux: OpenCV's bundled Haar face detectors if `opencv-python` is
installed), works on the upright image (EXIF orientation applied), and writes a new JPEG:

- `crop` (default; `photo_anonymise` in `coaich.md` or `--anonymise`): everything above a line just below the chin
  is cut off: the face box's bottom edge (or the lowest nose, eye or ear point, if lower) plus 12 % of the face
  height. The line must stay 30 % of the face height above the highest shoulder or neck point, so the neck, traps
  and shoulders stay; if it cannot, nothing is filed.
- `blur`: a solid grey block over the face box widened by 35 % each side and raised by 60 % (ears, hair), down to
  the same line. A flat fill, not a real blur: it leaves nothing to reverse.

It stops and writes nothing when there is no face, more than one, head points with no face box, or a face in the
lower 40 % of the picture. Two exceptions file the photo uncut (metadata still removed): a `back` pose with no
face and no nose or eye point, and `--user-cropped` (the user cut the face off) with no face found, or with no
detector at all. The new JPEG is written with no properties, then cleaned again in Python: all metadata removed
(EXIF incl. GPS, XMP, comments, PNG text/time chunks, anything after the image); a JPEG keeps only its colour
profile. The user's original stays where it was, untouched.

`photos/ratings.md`: a short header, then one Markdown table, one row per `date` + `group` (the key):

`| date | group | rating | confidence | note |`

`group` is a rubric id (`references/muscle-rubric.md`) with `rating` = `strong | adequate | lagging |
severely-lagging`, or `body-fat` with `rating` = `low-high` in % (e.g. `15-19`, at least 4 points wide).
`confidence` = `high | medium | low` (body fat is always `low`). Its midpoint goes to its own `body.csv` row,
`source = photo-range`.

`profile.md` fields of the physique skill: `photos_opt_in`, `ideal_physique` (the user's words),
`long_term_priorities` (program regions, used once the athlete is Advanced; `priority` stays the one region
`program-build` uses).

## The wellbeing gate (shared)

One function, `athlete_folder.gate(profile, feature)` (CLI: `athlete_folder.py gate nutrition|photos|physique`),
decides whether calorie targets (`nutrition`, also the roadmap's cut and bulk phases), photo reviews (`photos`)
and an ideal-physique analysis without photos (`physique`) are on. It returns the reasons they are off, in order:
`age` (under 18 by `age_band` or `age_years`), `age-unanswered`, `eating-disorder-history` (anything but an
explicit `no`), `eating-disorder-unanswered`, `wellbeing-pause`; plus `pregnancy` (nutrition only, a
`health_items` entry) and `no-photo-opt-in` (photos only).

## data/exercise_map.csv

`exercise, exercise_id` — every exercise name as logged → its free-exercise-db id, or `custom:<slug>` until
mapped. The importers add new names; the user (or the import skill) fixes a row and the next import applies it to
every set.

## profile.md — nutrition fields (v0.2)

Asked by `onboard` step 8 (optional, after the medical check); read by `scripts/nutrition.py`. The block sits
between `# --- nutrition` and `# --- end nutrition` in the template.

| field | values | notes |
|---|---|---|
| `age_years` | int | nutrition targets only from 18 |
| `sex` | `male` \| `female` \| `unspecified` | the energy formula and the body-fat bands only |
| `height` | `178 cm` \| `5 ft 10 in` | stored as typed; the script converts |
| `weight` | `80 kg` \| `176 lb` | used until `data/body.csv` has weigh-ins (and consent) |
| `activity` | `sedentary` \| `light` \| `moderate` \| `very` \| `extra` | starting multiplier; the weight trend replaces it |
| `eating_disorder_history` | `no` \| `yes` \| `prefer-not-to-say` | anything but an explicit `no` switches calorie targets and fat-loss phases off (photo reviews too, physique skill) |
| `wellbeing_pause` | `YYYY-MM-DD` or blank | **shared flag** (nutrition + physique + roadmap, through the gate): set by either skill when the user says something worrying (extreme restriction, purging, distress about body or food). While set: no calorie targets, no fat-loss phase, no photo reviews; the skill points to professional help. Only the user's explicit request clears it: the skill blanks it and adds a dated note under `# Profile` |
| `nutrition_phase` | `maintain` \| `gain` \| `lose` | |
| `rate_pct_week` | number or blank | % of body weight a week; lose is capped by body fat, gain at 0.5 |
| `body_fat_pct` | number, a range (`16-20`) or blank | a range counts as its midpoint; `data/body.csv` wins when it has one |
| `diet` | `omnivore` \| `pescatarian` \| `vegetarian` \| `vegan` | |
| `allergies` | list: `milk`, `egg`, `fish`, `shellfish`, `peanut`, `tree-nut`, `soy`, `gluten`, `sesame`, or other words | other words remove foods whose name contains them |
| `foods_avoid` | list of food ids or words | dislikes |
| `weight_tracking` | `yes` \| `no` | consent to read `data/body.csv` weigh-ins; `no` = profile `weight` only, no trend |

## plan/nutrition.md (v0.2)

Written only by `scripts/nutrition.py plan`. YAML header: `nutrition: 0.2`, `status: on | off`, `since`
(the date it came into force; the next weight-trend window starts here), and when on: `phase`, `rate_pct_week`,
`kcal`, `protein_g`, `fat_g`, `carbs_g`, `maintenance_kcal`, `maintenance_source` (`formula` | `weight-trend`),
`resting_kcal`, `weight_kg`; when off: `reason` (`age`, `eating-disorder`, `wellbeing-pause`, `pregnancy`). Body:
the targets, how each number was made, the safeguards applied and a day of meals. The script also keeps a
`<!-- coaich:nutrition -->` block in `plan/CURRENT.md`.

## plan/program.json

Schema: [program-schema.md](program-schema.md). Targets files (`plan/targets/`): the progression rules,
`skills/progression/rules.md`.

## plan/CURRENT.md blocks

Scripts own one block each, between `<!-- coaich:NAME -->` and `<!-- /coaich:NAME -->`, and replace only their
own: `program` (program_build.py), `roadmap` (roadmap.py: phase, program week, next easy week, gate review date),
`adapt` (adapt.py: pain and temporary constraints; its tag carries `days=`, `minutes=`, `until=` of a temporary
program, and its week-type rows `| W15 | Travel | 2030-04-08 | why |` are read by the progression engine).

## plan/roadmap.md

A YAML header holds the data; the body (phases, mesocycles, projected microcycles) is rewritten from it by
`roadmap.py`:

```
---
roadmap: 0.1
made: 2030-03-31
start: 2030-04-01
end: 2030-12-08
goal: both
level: intermediate
phases:
  - name: maintenance              # cut | bulk | maintenance
    start: 2030-04-01
    end: 2030-06-23
    status: current                # done | current | next
    gates: ["sessions_per_week 3..", "hit_rate 70..85", "e1rm:Barbell_Squat 5.."]
    result:                        # passed 2030-06-20 | missed 2030-06-20, extended 4 weeks | moved on, gates missed …
---
```

Gates are `metric band`, with the metrics and bands of `plan/changes.md` below.

## plan/changes.md

Every applied plan change, appended by the skill that made it (`adapt`, `monthly-check-in`, or by hand with
`scripts/changes.py add`). Entries are never edited; the monthly check-in adds one `graded` line once the check
date has come.

```
## c3 · 2030-03-31 · Swap Romanian Deadlift → Stiff-Legged Dumbbell Deadlift
- change: Romanian Deadlift → Stiff-Legged Dumbbell Deadlift wherever it ran
- why: the athlete's choice at the monthly check-in
- by: monthly-check-in
- metric: e1rm:Stiff-Legged_Dumbbell_Deadlift
- band: 0..
- check: 2030-04-28
- graded 2030-04-28: in band (+3.1 %; best e1RM 80.0 kg → 82.5 kg) · keep
```

| metric | unit | measured over applied → today |
|---|---|---|
| `hit_rate` | % | targets met ÷ (met + close + missed) in the graded weeks |
| `sessions_per_week` | sessions | program sessions logged a week |
| `e1rm:<exercise_id>` | % | best Epley estimate (working sets of 1–12 reps, easy weeks out): the 4 weeks before against the last 2 |
| `sets:<muscle or group>` | sets/week | effective sets (direct ×1, secondary ×0.5), full weeks, easy weeks out |
| `weight_rate` | %/week | least-squares slope of `body.csv` weight (6+ weigh-ins over 2+ weeks) |
| `ask` | — | not measurable: the check-in asks the athlete |

A band is `lo..hi`; either side may be blank (`5..`, `..-0.25`). Verdicts: in band (keep) · below or above band
(adjust or revert: the athlete decides) · too early · no data.

## log.md

Header `# Log`, then one line per skill run, exactly:

```
- YYYY-MM-DD · <skill> · <one-line result>
```

The date is the run date; ` · ` is space, middle dot (U+00B7), space; the result is one line (line breaks become
spaces). Importers write `- YYYY-MM-DD · import · <source>: <n> sessions, <m> sets through YYYY-MM-DD` (Apple
Health: `apple-health: <n> days through YYYY-MM-DD`). The progression engine reads the newest `· import ·` date as
"the data is complete up to here" (its stale-data guard).
