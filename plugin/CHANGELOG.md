# Changelog

CoAIch follows [docs/versioning.md](../docs/versioning.md): semantic versioning; 0.x is a preview with no hero
name, or the next hero's name with "preview" after it.

## Unreleased

## 0.6.0 — Achilles preview

Changed (a review against Stronger By Science's articles and the primary studies; numbers come from the
studies, never copied from the site)
- `program-audit`: G2, a group over the MRV coaching band, is a note, not a failure. A gate needs a study behind
  its direction; MRV is a practitioner band and Pelland 2025 found smaller returns but no ceiling.
- `program-build`: with the strength goal, main lifts aim at 2–3 reps left (was 1–2 or 2): strength gains hold
  further from failure, at lower fatigue (Robinson 2024). Muscle goal and beginners unchanged.
- `progression`: a second miss in a row repeats the target once more (`miss2_hold`, flagged for review); the
  lighter target comes after a third miss (was the second). Both are practitioner rules; this one is gentler.
- `progression`: a reduce from sets over 12 reps says it is a rough guide (rep-max formulas drift there).
- `roadmap`, `physique`: goals are rates, never dated body-fat targets.
- Nutrition (experimental): protein and fat rules checked against PubMed and kept; Morton 2018's exact
  confidence interval, Helms 2014 (lean athletes in a deficit) and Whittaker 2021 (low-fat diets and
  testosterone) cited.

Fixed
- A reason saved by an older version renders even when a newer version added a field to its sentence.

## 0.5.0 — Achilles preview

Added
- Send routines to Hevy: after the weekly review applies the targets, and with the athlete's yes, the week's
  targets go to the athlete's Hevy routines (one per program routine, titled "<routine> · CoAIch", with rest,
  rep range and each target's reason as the note), then are read back and checked. `program-build` uses the same
  path for a new program (no weights yet). `scripts/hevy_routines.py` builds the routines from applied targets
  only and checks the read-back; Claude sends them through the Hevy MCP server (needs Hevy Pro), creating or
  updating by title and never deleting. Exercise matches live in the new `data/hevy_templates.csv`, learned from
  imported Hevy workouts or picked by the athlete.

## 0.4.0 — Achilles preview

Fixed
- Coming back after 14+ days off: the first week back is still not graded, but what you lift that week now sets
  the next target (heaviest sets as logged, each capped at the target from before the break; a lower load needs
  your OK). Before, the old target came back unchanged, however long the break. `adapt` tells you to go lighter
  in that first week (3–4 reps left on every set). New reason `reentry_start`.

## 0.3.0 — Achilles preview

Changed
- `nutrition` and `physique` are **experimental**: off unless `coaich.md` says `experimental: on` (new setting;
  absent = off), because their safety wording has not had a legal review yet. The shared gate reports
  `experimental-off` first and still reports every safety reason, so switching it on never skips them; roadmap
  cut and bulk phases, the monthly check-in's nutrition section and photo filing follow it. `onboard` asks before
  the optional nutrition and photo questions. Existing folders: add `experimental: on` to keep them. Training is
  unaffected.

Added
- `/feedback` (user-invoked): drafts an idea or question for GitHub Discussions, or a problem for the bug
  form, with the plugin version and operating system. The user reads it and posts it themselves; nothing is sent.
  Warns about text that looks personal (email, phone, dates, body numbers). An optional count of skill runs over the
  last 90 days from `log.md` is attached only after a yes. `scripts/feedback.py`.
- `import`: openGym. `import_opengym.py` reads openGym's JSON backup (Settings > Data & backup > Export backup)
  into `sets.csv` and `sessions.csv` (done sets only; warm-ups, failure and drop sets kept as set types; lb to kg)
  and its weigh-ins into `body.csv` (source `opengym`). Safe to run again. Built-in exercise names come from a
  local openGym checkout (`--catalogue`) or, after the user's OK, from openGym's GitHub (`--fetch-names`, numbers
  only sent, cached in `data/opengym_names.json`); without them, `openGym <id>`.
- `setup` (`/setup`, first step of `onboard`): where CoAIch runs, language, units, data sources (Strong, Hevy MCP or
  CSV, openGym, Apple Health, or by hand) and how data arrives, saved in `coaich.md`; `scripts/setup.py check`
  says what works and how to fix what doesn't. New `coaich.md` keys `runtime` and `link` (absent = the defaults,
  `claude-code` and `file`); `data_sources` gains `hevy-csv` and `opengym`. Existing folders need no change.
  Apple Health is offered for steps, weight, sleep and body measurements (Health Auto Export JSON), not
  workouts; the Health app's `export.zip` is refused with that advice.
- `physique`: the face is removed on the user's computer before Claude sees a photo. Default: cut just below the
  chin (neck, traps and shoulders kept); `blur` covers the face with a solid block. Apple Vision on macOS
  (`scripts/anonymise.swift`), OpenCV if installed elsewhere; no face, several faces or a chin too close to the
  shoulders → nothing is filed and the user crops it. Only the anonymised copy is kept; Claude never opens the
  original. Setting `photo_anonymise: crop | blur` in `coaich.md`.
- `physique`: a back view is never cut, so arms raised beside the head stay (back double biceps): a grey block
  covers the back of the head, placed from the ears, neck and shoulders. No neck and shoulders found → nothing is
  filed.

## 0.2.0 — preview

Added
- `nutrition` (model-invoked): calories, protein, fat and carbs with every step shown, a day of meals from the
  bundled USDA food table (diet, allergies, dislikes), maintenance from the weight trend. Safeguards in code:
  18+ only, the eating-disorder question first (only an explicit "no" opens targets), pregnancy turns targets off,
  never below resting needs, a weekly loss cap by body fat, no fat loss below BMI 18.5.
- `physique` (model-invoked, opt-in, 18+): progress photos filed with their metadata stripped, muscle-group
  ratings against one rubric, comparisons between sets, an optional rough body-fat range, goal-physique priorities.
- `monthly-check-in` (user-invoked): four weeks of trends, past plan changes graded against their bands
  (`plan/changes.md`), nutrition and physique when on, next month's program and roadmap position.
- `adapt` (model-invoked): pain (red flag → a professional and the area left out; otherwise same-slot swaps) and
  temporary constraints (fewer days, less time, travel), then back to normal. Every version passes the audit.
- `roadmap` (model-invoked): a dated macrocycle of phases with gates, mesocycles and projected microcycles; cut and
  bulk phases only behind the nutrition safeguards.
- One wellbeing gate shared by nutrition, physique and the roadmap (`athlete_folder.py gate`), with one set of
  `profile.md` fields: `age_years`, `eating_disorder_history`, `wellbeing_pause`, `photos_opt_in`,
  `nutrition_phase`, `ideal_physique`, `long_term_priorities`, `exercise_swaps`. A worrying remark in either skill
  sets `wellbeing_pause`: no calorie targets and no photo reviews until the athlete asks.
- `weekly-review` shows one weight-trend line when nutrition is on (`nutrition.py trend --line`: on track, eat
  more, slower or faster than planned; it never says "eat less").
- The demo athlete has nutrition on (a slow lean gain, morning weigh-ins); photos stay off.

Changed
- `data/body.csv` is keyed by `date` + `source` (was `date`): a scale reading and a photo body-fat range on the same
  day both stay; readers pick one value per date (by hand, scale, Apple Health, photo range). Existing v0.1 files
  read as before; the Apple Health importer now writes only its own rows.
- A promotion (re-issue at a new level) restarts the easy-week count: `plan/program.json` records
  `easy_from_week`, so the week after a promotion is never an easy week.
- Easy weeks are counted in sessions done everywhere (builder, progression, roadmap); a re-issue keeps week 1's
  date.
- The monthly check-in lists muscles below the usual coaching band as information only: no alarm and no automatic
  set increase (the weekly engine stays in parity with the iPhone app).

## 0.1.0 — preview

- `onboard`, `safety` (medical gate, red-flag pain rule), `import` (Strong CSV, Hevy MCP or CSV, Apple Health via
  Health Auto Export), `program-build` (starter programs from the placement tree, audit-gated), `progression`
  (grade last week, propose next week's targets with reasons), `weekly-review`, `program-audit`.
- The athlete-folder contract (`docs/athlete-folder.md`) and the program schema (`docs/program-schema.md`).
- The demo athlete "Sam": 12 weeks in 2030, generated by the real engine and checked by a staleness test.
