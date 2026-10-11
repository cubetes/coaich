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

## 8. v0.2 hooks

<!-- v0.2 nutrition hook (nutrition lane): 18+ only, eating-disorder question first → `eating_disorder_history`. -->
Nutrition is not in this version yet. If the user asks, say it comes in a later version.

### Photos and ideal physique (18+ only)

Skip this whole step when `age_band` is `under-16` or `16-17`, or `eating_disorder_history: yes` (the nutrition
step's answer: read it, never ask it twice). If `eating_disorder_history` is not answered, skip it too; the
`physique` skill asks it when the user first wants a photo review.

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
