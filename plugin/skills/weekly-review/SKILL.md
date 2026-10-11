---
name: weekly-review
description: The weekly training loop. Read the week's sets, grade last week's targets, propose next week's with reasons, get the athlete's OK, apply, and write the check-in. Use once a week, after the last session.
disable-model-invocation: true
---

# Weekly review

One pass, in order. The athlete folder is the working directory (it holds `coaich.md`). Read
`plan/CURRENT.md` first: it wins over every other file. Write in the language `coaich.md` sets.

`{today}` = today's date. `{last}` = the ISO week just finished. `{next}` = the week starting next
Monday.

## 1. Make sure the week is in

Check `data/sets.csv` has sessions dated in `{last}`. If the athlete trained since the last import,
run the `import` skill first. Ask once: "Anything you did that isn't logged?" Missing sessions are
graded "not done", which is fine, but it should be true.

## 2. Grade and propose

Run the `progression` skill, step 1 (`propose --week {next}`). It grades `{last}` and drafts
`{next}`. Keep the printed tables: they go into the check-in.

## 3. The week in numbers

From the propose output and `data/`:

- Sessions done vs planned, and the targets met (`targets met x/n (y %)`) with the hit-rate band
  line exactly as printed.
- Optional, only if `data/health.csv` has the week: average sleep, steps and resting heart rate
  against the previous 4 weeks, one line each. Context only. Never call fatigue on fewer than two
  signals that agree (a low hit rate plus worse sleep, say).

## 4. Ask

Show the exceptions as the `progression` skill says (ask rows first, each with before → after and
why). Then ask the athlete to confirm, change or reject. Every ask row needs its own yes.
"No changes this week" is a fine answer.

## 5. Apply

Run the `progression` skill, step 3, with exactly what the athlete confirmed. Never approve a
spine-loaded increase the athlete did not OK by name.

## 6. Write the check-in

Write `check-ins/{today}-weekly.md`:

```
# Weekly check-in · {today} · {last}

## The week
<sessions done / planned · targets met · band line · health lines if any · athlete notes, verbatim>

## Grades
<the grade table from the propose output>

## Next week ({next})
<the applied targets the apply step printed>

## Decisions
<each change: before → after · why · evidence window; each ask row: OK'd or held; or "No changes this week">
```

## 7. Log

Append one line to `log.md`: `{today} · weekly-review · {last} graded, x/n met, k changes, m held`.

## Out of scope in this version

Nutrition, photos, body weight trend and wearable sync. If the athlete asks, say they come in a
later version and keep to training.
