---
name: progression
description: Grade last week's targets and propose next week's target per exercise, each with its reason. Use when new sessions are in and the athlete needs targets, or asks "what should I lift next week".
---

# Progression

One script does the numbers: `${CLAUDE_PLUGIN_ROOT}/scripts/progression.py`. Never work out a
target by hand. Rules, reason codes and the `program.json` fields it reads: [rules.md](rules.md).

Run from the athlete folder (the one holding `coaich.md`). `{last}` = the ISO week just finished,
`{next}` = the week starting next Monday (e.g. `2030-W10` / `2030-W11`).

## 1. Propose

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/progression.py" propose --dir . --week {next}
```

It grades `{last}` first (safe to repeat) and prints a Markdown table per routine: last target,
what was done, the grade, the next target, why, and "ask" on rows that need an OK.

- **REFUSED, stale data**: the sets stop before the end of `{last}`. Import first (`import`
  skill). If the athlete says the week is complete as it is (a rest Sunday), re-run with
  `--data-through YYYY-MM-DD`.
- **REFUSED, frozen**: `{next}` is already applied. Do not force it; say what is in force.

## 2. Show exceptions first

Lead with what needs a decision, not every row:

1. Every **ask** row: load increases on spine-loaded lifts, every reduce after three misses, every
   swap. Each needs its own explicit OK. A general "ok" does not cover them.
2. Misses, `coach_review`, `not_done_x2`, and every row with an athlete's note (quoted as written).
3. One line for the rest ("9 go up, 12 stay the same").

"No changes this week" is a valid outcome. Never invent a change to fill the table. A coach change
on top of the engine (override, swap) follows the evidence rules in [rules.md](rules.md): enough
history, ≥ 2 stalls or the athlete's own note, at most 6 per review, each stated as
`before → after · why · evidence window`.

Words: say "reps left", "easy week", "starting weight". Never "RIR", "RPE" or "deload".

## 3. Apply what the athlete confirmed

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/progression.py" apply --dir . --week {next} \
  --accept-all [--approve id,id] [--override "id=KGxR·R·R:reason"] [--reject id,id]
```

- `--approve` only the ask rows the athlete OK'd one by one.
- An override needs a reason; it cannot raise a spine lift without `--approve` for that id.
- Athlete absent (skipped check-in): `--auto-isolation-only`. Isolation rows move; the rest hold.

The script prints next week's targets. That list is what the athlete trains to.

## Fixing a graded week

A session deleted or added after grading: `grade --dir . --week {last} --force`, then
`propose --week {next} --force`. Allowed only while `{next}` is not applied. Once applied, the
script refuses: put the correction in the check-in text and leave the file alone.
