---
name: onboard
description: Set up your training folder and answer the intake questions. Run once, or again to redo your answers.
disable-model-invocation: true
---

# Onboard

One-time setup, then the intake. Writes `coaich.md` and `profile.md`, then hands off to `import` and
`program-build`. The data contract is `docs/athlete-folder.md` in this plugin.

Ask **one question at a time**, offer the answers as a short list, and accept a number or the words. Plain words
only: no "RIR", "deload", "hypertrophy" or "1RM" in questions. In `language: es`, use
[questions-es.md](questions-es.md) for the wording.

## 1. Find or create the folder

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" find`.

- **Found, `profile.md` has a `history`** → *"You're already set up. Redo your answers, or keep them?"* Keep →
  stop here. Redo → go on; answers are replaced, data files are never touched, and the recorded doctor's
  clearance is blanked (`safety_clearance_date`, `safety_clearance_sentence`): the safety intake asks again.
- **Not found** → *"Make this folder your training folder? ({cwd})"*. Yes, or a path the user gives →
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" init <dir>`.

Then say once, exactly:

> Your training data stays in this folder. It passes through your own Claude session, so Anthropic processes it
> under your account's terms. Nothing goes to a CoAIch server: there isn't one. Hevy or Apple Health only get
> involved if you turn them on.

## 2. Settings → `coaich.md`

1. *"English or Spanish?"* → `language: en | es` (default en).
2. *"Kilograms or pounds?"* → `units: kg | lb` (files always store kg).
3. *"Where are your past workouts?"* Strong (CSV export) · Hevy (needs Hevy Pro and the Hevy MCP server) ·
   Apple Health (export file) · Nowhere yet → `data_sources: [strong-csv | hevy-mcp | apple-health]`.

## 3. Age → `profile.md`

*"How old are you?"* Under 16 · 16 or 17 · 18 to 59 · 60 or over → `age_band: under-16 | 16-17 | 18-59 | 60+`.

## 4. Health and pain

Call the Skill tool with `safety` and run its **Intake**. If the status comes back `stop`, write what you have,
log it, tell the user they can run `/onboard` again after the clearance, and end.

## 5. Training

1. *"How long have you trained with weights? Only count periods when you went 2 or more times a week."*
   Never, or under 6 months in total · 6 months to 2 years · More than 2 years → `history: never | 6m-2y | over-2y`.
2. Not "never": *"When did you last train like that for at least a month?"* In the last 3 months · 3 to 12
   months ago · More than a year ago → `last_trained: last-3m | 3-12m | over-1y`.
3. More than 2 years and last 3 months: *"Do you know the weight you usually use on squat and bench press for
   about 8 reps?"* Yes (kg × reps for each) · I don't know, or I don't do those → `known_loads`.
4. *"How many days a week will you really train? Pick what you can keep up for a month."* 2 · 3 · 4 · 5 · 6.
5. *"How long do you have per session, warm-up included?"* About 30 min · 45 · 60 · 75 or more.
6. v0.1 plans are for a gym: `equipment: gym`. If the user trains at home, say *"Home plans come in a later
   version."* and go on.

## 6. Placement

Never work out the level yourself: the placement tree lives in `program_build.py` only. Write the answers so far
(steps 3 to 5) into the front matter of `profile.md`, then run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/program_build.py" --dir <folder> --place
```

It prints JSON: `level`, `returning`, `promotion_check_week`, `advanced_check_week` and `line`, the sentence to
say (in `language: es`, say it in Spanish, as in [questions-es.md](questions-es.md)). Exit 2 names a missing or
bad answer: ask that question again. The level is not written to `profile.md`; `program-build` places the
athlete again from the same answers and records it in `plan/program.json` (`level`, `placement`).

Then, by the printed `level`:

- 60+ and beginner: *"Can you stand up from a chair 5 times in a row without using your hands?"* → `chair_stand`.
- Intermediate or advanced: *"What do you want most?"* More strength · More muscle · Both → `goal`. Beginners:
  `goal: both`.
- Advanced: *"Want to give one area priority?"* None · Chest · Back · Shoulders · Arms · Quads · Glutes and
  hamstrings · Calves → `priority`.

Tell the user the placement with the printed `line`, e.g. *"We've put you in Intermediate: 6 months to 2 years
of lifting, and you trained in the last 3 months."*

## 7. Write and log

Write every answer into the front matter of `profile.md` (field names as in the template), set `updated` to
today, add any free-text remarks under `# Profile`. Then:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" log onboard "<level from --place>, <days> days, <minutes> min, goal <goal>"`.

## 8. Nutrition and photos (optional)

### 8a. Nutrition (optional)

Only when `age_band` is `18-59` or `60+`; for `16-17` say *"Nutrition targets are for ages 18 and over."* and
skip. Ask one question at a time; write each answer into the nutrition block of `profile.md` (field names in
`docs/athlete-folder.md`). Never work out a number yourself: `nutrition.py` does all of it.

1. *"Do you want help with food too: daily calories, protein and a sample day of meals?"* Yes · Not now. Not
   now → skip 8a (they can ask the `nutrition` skill later).
2. Before any number, ask exactly once: *"Have you ever had an eating disorder, or been treated for one?"*
   No · Yes · I'd rather not say → `eating_disorder_history: no | yes | prefer-not-to-say`. Do not ask follow-up
   questions. Anything but **No** → run the script (step 11) at once: it switches calorie targets off and prints
   the wording to say. Then skip the rest of 8a.
3. *"How old are you, in years?"* → `age_years`.
4. *"For the energy formula: male, female, or rather not say?"* → `sex: male | female | unspecified`.
5. *"How tall are you?"* (cm, or feet and inches) → `height` as typed, e.g. `178 cm`, `5 ft 10 in`.
6. *"What do you weigh now?"* (kg or lb) → `weight` as typed, e.g. `80 kg`.
7. *"How active is a normal week, gym included?"* Mostly sitting, little exercise · Mostly sitting, training 1–3
   days · Training 3–5 days, or on my feet a lot · Training 6–7 days, or a physical job and training · A hard
   physical job and hard training most days → `activity: sedentary | light | moderate | very | extra`.
8. *"What do you want your weight to do?"* Stay about the same · Go up slowly, to build muscle · Go down, to lose
   fat → `nutrition_phase: maintain | gain | lose`. Lose → *"Do you know your body fat roughly? A range is fine,
   like 16–20 %. Or skip."* → `body_fat_pct` (as given). Say: *"We start at 0.5 % of your weight a week. The
   fastest we go depends on your body fat."*
9. *"Do you eat everything, or no meat, no meat or fish, or nothing from animals?"* → `diet: omnivore |
   pescatarian | vegetarian | vegan`. *"Any food allergies or intolerances?"* → `allergies` (milk, egg, fish,
   shellfish, peanut, tree-nut, soy, gluten, sesame, or the user's words). *"Anything you won't eat?"* →
   `foods_avoid`.
10. *"Can CoAIch read your weigh-ins (`data/body.csv`) each week to check your trend and correct the calories?
    They stay in this folder."* Yes · No → `weight_tracking: yes | no`.
11. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/nutrition.py" plan --dir <folder>`. Exit 0 → say the daily
    targets line and that the full plan is in `plan/nutrition.md`. Exit 3 → say its output word for word (a
    safeguard). Exit 2 → ask the question it names again. The script writes the log line.

`wellbeing_pause` is never asked: the `nutrition` and `physique` skills set it (see the nutrition skill). While it is
set there are no calorie targets and no photo reviews.

### 8b. Photos and ideal physique (optional, 18+ only)

Skip this whole step when `age_band` is `under-16` or `16-17`, or `wellbeing_pause` is set. If
`eating_disorder_history` is blank (the user skipped 8a), ask 8a's question 2 now, exactly once, and write the
answer. Anything but **No** → skip this step: photo reviews stay off (`scripts/athlete_folder.py gate` says why).

1. *"Do you want to use progress photos? I'd rate how each muscle group is coming along, compare them over time
   and help you pick what to train most. Your photos stay in this folder, pass only through your own Claude
   session, and their location and camera data are removed when they are filed. You can switch this off any
   time."* Yes · No → `photos_opt_in: yes | no`. Only an explicit yes counts.
2. *"Is there a look you're aiming for? Describe it in a few words, or say no. (For example: wider shoulders,
   bigger arms, stronger legs.)"* → `ideal_physique: "<their words>"`, or leave it blank. If they share a picture
   of someone, note only which muscle groups it stresses, never who it is. Do not rank anything now: the
   `physique` skill does that.

Write both answers to the front matter of `profile.md`.

## 9. Hand off

1. `data_sources` not empty → call the Skill tool with `import` so past sessions inform the first targets.
2. Call the Skill tool with `program-build`.
