---
name: adapt
description: Fit the plan around pain or an injury, or around a temporary change in days, session time or travel, then back to normal. Use when the user says something hurts, they injured something, they can only train N days or M minutes for a while, they are travelling, or the pain or the constraint is over.
---

# Adapt

One script makes every change: `${CLAUDE_PLUGIN_ROOT}/scripts/adapt.py`. It rebuilds the program through
`program_build.py`, so the audit gates every version; it writes each change to `plan/changes.md` with its success
band and logs it. Never edit `plan/program.json`, `profile.md` pain or `plan/CURRENT.md` by hand around it.

Run from the athlete folder. Read `plan/CURRENT.md` first. `language: es` → answer in Spanish; the safety wording
comes from the safety skill's [copy-es.md](../safety/copy-es.md).

## Pain or injury

CoAIch never classifies an injury (no "acute", "phase" or likely cause). Only one question decides the path:

1. Say the safety skill's red-flag question: *"Is it strong, sharp, recent, swollen or spreading?"* Chest pain,
   fainting or severe breathlessness → the safety skill's emergency wording, now, and stop.
2. Area: knee, lower back, shoulder, elbow or wrist, hip, somewhere else (`knee`, `lower-back`, `shoulder`,
   `elbow-wrist`, `hip`, `other`).
3. Preview, then apply after the athlete's yes:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/adapt.py" injury --dir . --area <area> --red-flag|--no-red-flag --dry-run
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/adapt.py" injury --dir . --area <area> --red-flag|--no-red-flag
```

- **Red flag**: the script prints the safety wording (see a physiotherapist or doctor; the exercises that load
  the area are left out). Say it word for word, first.
- **No red flag**: safer exercises in the same slots ("stop what hurts; if it gets worse, see a professional").
- **Lower back, either way**: no spine-loading exercise stays in the program or its alternatives (squats,
  deadlifts, standing presses, barbell rows, leg press, lunges). The audit refuses any program that breaks this.
- **Somewhere else**: nothing maps to it. Say: stop any exercise that hurts, and see a professional if it is a
  red flag or gets worse. Do not guess which exercises load it.

Show the "Change cN" line: what came out and what went in, by session.

## Back to normal after pain

| The athlete says | Run | What happens |
|---|---|---|
| a professional checked the red-flag area | `checked --area <area>` | its slots come back, with the safer exercises |
| the pain is gone | `clear --area <area>` | the area leaves `profile.md`; the full program returns |

Both print the return rule: the first session of each returning exercise sets its weight (a weight they could lift
for the top of the range with 3–4 reps left); the weekly review builds from there. Never skip `checked` for a red
flag on the athlete's word that it "feels better": ask whether a professional checked it.

## Temporary constraint (days, time, travel)

Gym only in this version: no home or hotel programs; say so if asked.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/adapt.py" constraint --dir . --from YYYY-MM-DD --to YYYY-MM-DD \
  [--days N] [--minutes M] [--no-gym] [--dry-run]
```

| Constraint | What the script does |
|---|---|
| up to 14 days, fewer days or minutes | those weeks run **moderated**: one set fewer per exercise; sessions run in order, what is not done holds its target; misses there do not count towards a reduce |
| no gym (any length), or 0 days | **travel** weeks: targets frozen, nothing graded; 14+ days off makes the first week back a re-entry week (not graded) |
| over 14 days, 2+ days a week | a temporary program for those days and minutes, until `--to` |

If the script says a week's targets are already applied, run the `progression.py propose … --week-type … --force`
line it prints, then apply, so the week is not graded as a full week.

On or after the end date of a temporary program (`status` says DUE; the weekly review checks it):

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/adapt.py" restore --dir .
```

It rebuilds the normal program from `profile.md` at the current program week; the easy-week count carries on.

## Status

`adapt.py status --dir .` lists the pain areas, the constraints and anything due.

## Never

- Diagnose, name a cause, suggest treatment, or call an injury acute, sub-acute or chronic.
- Put back a red-flag area's exercises before a professional has checked it.
- Change a plan while `safety_status` is `stop` (the script refuses).
