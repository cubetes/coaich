# The athlete folder — data contract (v0.1)

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
  photos/YYYY-MM-DD/     front.jpg|png, side.*, back.* with metadata stripped (v0.2, git-ignored)
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
| `body.csv` | `date` |
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
estimate range midpoint). `source` = `scale` | `apple-health` | `photo-range` | `manual`. An Apple Health import
fills only the fields it has and keeps values typed by hand.

## data/health.csv (long format)

`date, metric, value, unit, source` — metrics: `steps`, `sleep_h`, `hrv_ms`, `resting_hr_bpm`, `active_kcal`,
`vo2max`, `weight_kg` (weight also lands in body.csv). Source: `apple-health`.

## photos/ (v0.2, physique skill)

Only for athletes 18 or over with `photos_opt_in: yes` and `eating_disorder_history: no` in `profile.md`;
`scripts/photos.py` refuses every write otherwise. `photos/YYYY-MM-DD/` holds one file per pose, `front`, `side`
and `back` (`.jpg` or `.png`), dated by the day they were taken. `photos.py file` copies them in with all
metadata removed (EXIF incl. GPS, XMP, comments, PNG text/time chunks, anything after the image); a JPEG keeps
only its orientation and colour profile. The whole `photos/` folder is git-ignored by the template.

`photos/ratings.md`: a short header, then one Markdown table, one row per `date` + `group` (the key):

`| date | group | rating | confidence | note |`

`group` is a rubric id (`references/muscle-rubric.md`) with `rating` = `strong | adequate | lagging |
severely-lagging`, or `body-fat` with `rating` = `low-high` in % (e.g. `15-19`, at least 4 points wide).
`confidence` = `high | medium | low` (body fat is always `low`). Its midpoint goes to `body.csv` as
`source = photo-range`, unless that date's row already holds another source's reading.

`profile.md` fields of the physique skill: `photos_opt_in`, `ideal_physique` (the user's words),
`long_term_priorities` (program regions, used once the athlete is Advanced; `priority` stays the one region
`program-build` uses).

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
| `wellbeing_pause` | `YYYY-MM-DD` or blank | **shared flag** (nutrition + physique): set by either skill when the user says something worrying (extreme restriction, purging, distress about body or food). While set: no calorie targets, no fat-loss phase, no photo reviews; the skill points to professional help. Only the user's explicit request clears it: the skill blanks it and adds a dated note under `# Profile` |
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

## log.md

Header `# Log`, then one line per skill run, exactly:

```
- YYYY-MM-DD · <skill> · <one-line result>
```

The date is the run date; ` · ` is space, middle dot (U+00B7), space; the result is one line (line breaks become
spaces). Importers write `- YYYY-MM-DD · import · <source>: <n> sessions, <m> sets through YYYY-MM-DD` (Apple
Health: `apple-health: <n> days through YYYY-MM-DD`). The progression engine reads the newest `· import ·` date as
"the data is complete up to here" (its stale-data guard).
