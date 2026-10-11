---
name: program-build
description: Build the athlete's training program from their intake answers and explain every choice. Use after onboarding, when the user asks for a new or different program, or when CURRENT.md says to rebuild at this week.
---

# Program build

A fixed decision tree turns `profile.md` into a program: level, layout, time version, then goal, priority, age
and pain adapt it. The script does every number; you explain it. Never invent sets, reps or exercises: if the
user wants something the tree does not give, say so and offer `program-audit` on their own version.

Rules and sources: [starter-programs.md](../../references/starter-programs.md),
[evidence.md](../../references/evidence.md). Output format: [program-schema.md](../../docs/program-schema.md).

## 1. Safety first

Call the Skill tool with `safety` unless it ran in this conversation and `coaich.md` shows `safety_status` go
or warn. A `stop` ends here: repeat the safety skill's wording, build nothing.

## 2. Answers

Find the folder: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" find`. Read `profile.md`. The script
needs `age_band`, `history`, `last_trained` (unless history is never), `days_per_week`, `minutes_per_session`;
`goal` for intermediate and up; `chair_stand` for 60+ beginners; `known_loads` and `priority` only matter for
advanced. Missing → run that question from `/onboard` (one at a time), write it to `profile.md`, go on.

A changed answer ("I can only do 3 days now") → update `profile.md` first, then build. Never pass answers any
other way.

## 3. Build

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/program_build.py" --dir <folder> [--week N]
```

`--week` = the program week counted in sessions done (default 1; use `rebuild_at_week` from `CURRENT.md` when
rebuilding). Add `--dry-run` to preview without writing.

| Exit | Meaning | Do |
|---|---|---|
| 0 | wrote `plan/program.json`, the program block of `plan/CURRENT.md`, a `log.md` line | step 4 |
| 1 | the audit refused the program | show the failures, write nothing by hand, report it as a bug |
| 2 | stop: medical gate, under 16, or a bad answer | show the message; fix the named key or hand back to `safety` |

## 4. Explain

Read the program block in `plan/CURRENT.md` and present it. The block's **Why this program** list is the spine
of your answer: one reason per choice, in plain words, each with its source kind (a study, or "our rule"):

- **Level** and why (history and recency, never a self-label; ambiguous answers go down).
- **Layout and days**, and any cap ("4 days at most for your first 12 weeks").
- **Time**: the longest session against their minutes.
- **Reps and effort**: rep ranges, "reps in reserve" explained once as *how many more you could have done*;
  spine lifts always 2 or more short of failure.
- **Every swap** in `swaps` and every slot in `left_out`, with the area it protects.
- **Easy weeks**: when, and what an easy week is.
- **Warnings** verbatim, first, before any table. **Notes** after.

Then the sessions table, the alternatives, and: sessions run in order, not by weekday. End with what happens
next: log the sessions (or `/import`), then `/weekly-review` grades them and sets next week's targets.

## 5. Optional: push to Hevy

Only if `data_sources` has `hevy-mcp` and the user says yes. Create or update routines by title, one per
`routines[]`, sets from `sets` and `rep_range`. Then read the routines back and confirm they match before saying
it worked. Never delete anything in Hevy.
