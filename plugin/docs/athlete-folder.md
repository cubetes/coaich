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
  plan/program.json      routine spec (no vendor ids; exercises by free-exercise-db id)
  plan/targets/          targets_YYYY-Www.json, one per ISO week
  plan/changes.md        dated plan changes, each with its success band
  plan/nutrition.md      macros + meal plan (v0.2)
  data/sets.csv          one row per set (schema below)
  data/sessions.csv      one row per session (schema below)
  data/body.csv          body measurements (schema below)
  data/health.csv        daily wearable metrics, long format (schema below)
  data/exercise_map.csv  source exercise name → exercise_id (the fix-up list)
  data/raw/              untouched exports (git-ignored)
  photos/YYYY-MM-DD/     front/side/back + photos/ratings.md (v0.2)
  check-ins/             YYYY-MM-DD-weekly.md, YYYY-MM-DD-monthly.md
  log.md                 one line per skill run: date · skill · one-line result
```

All weights are stored in **kg** (lb converted on import, `coaich.md` sets the display unit). Dates are ISO 8601,
local time, `datetime` = `YYYY-MM-DDTHH:MM`. CSV: UTF-8, comma, header row, no index column. Importers are
**idempotent**: re-importing the same export never duplicates rows (key = `session_id` + `exercise` + `set_index` for sets, since `set_index` restarts for each exercise;
`session_id` for sessions, `date` + `metric` for health, `date` for body).

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
estimate range midpoint, with `source` = scale|photo-range|manual).

## data/health.csv (long format)

`date, metric, value, unit, source` — metrics: `steps`, `sleep_h`, `hrv_ms`, `resting_hr_bpm`, `active_kcal`,
`vo2max`, `weight_kg` (weight also lands in body.csv). Source: `apple-health`.
