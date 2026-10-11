---
name: monthly-check-in
description: The monthly review of the mesocycle. Four weeks of trends (targets met, volume per muscle, main lifts, body weight, health), whether past plan changes worked, nutrition and photos when they are on, then next month's program and roadmap position, with the athlete's OK. Use once a month, after that week's weekly review.
disable-model-invocation: true
---

# Monthly check-in

One pass, in order. The athlete folder is the working directory. Read `plan/CURRENT.md` first: it wins over every
other file. Write in the language `coaich.md` sets. Every number comes from a script; copy it, never recompute.

`{today}` = today. When the newest session in `data/sets.csv` is weeks away from today (an old export, the demo
athlete in 2030), ask which date to review and use it as `--today` everywhere.

## 1. Gate and data

- Call the Skill tool with `safety` unless it ran in this conversation. `stop` → report only (steps 2–4); propose
  and change nothing.
- The month's last week must be graded: if the weekly review for it has not run, run `/weekly-review` first
  (it imports and grades). Ask once: "Anything you did this month that isn't logged?"

## 2. The report

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/monthly_check_in.py" report --dir . --today {today}
```

It prints the sections of the check-in: the month (sessions and targets met per week, the hit-rate band line),
volume per muscle against the coaching bands, main lifts (estimated best single, the previous 4 weeks against
the last 2), rows the weekly loop flagged, body weight trend, a health glance, past changes graded against their
bands, the roadmap position with gates when due, and the signals for next month. Keep it: it becomes the check-in.

How to read it, in plain words:

- **Volume**: "effective sets" counts an exercise's main muscle as 1 set and each helper muscle as half. The
  bands (MEV, MAV, MRV) are coaching practice, not study cut-offs: say "below the usual coaching band", never
  "below the minimum". Only MRV is a gate. A low direct count with enough effective sets is fine.
- **Health**: context only. Never call fatigue on fewer than two signals that agree.
- **Past changes**: each change in `plan/changes.md` is graded once its check date has come: in band → keep;
  below or above band → adjust or revert (ask the athlete); no data → say it could not be measured, never guess;
  too early → its check date. "Not measurable" and "too early" are honest answers, not failures.

## 3. Nutrition and physique (only when on)

The report's last section says whether each is on (their own safeguards decide).

- **Nutrition on** → call the Skill tool with `nutrition`, step "adjust from the weight trend", for this month.
- **Physique on** → ask for this month's photos; if they are given, call the Skill tool with `physique` (compare
  with the last set).

Never reimplement either here; their outputs join the check-in as a short section each, as they print them.

## 4. Roadmap

If the report says "No roadmap yet", offer the `roadmap` skill (optional). If a phase's gates are due, run the
`roadmap` skill's step 4 (check, then the athlete picks passed, missed or move on).

## 5. Propose next month

Build the proposal from the report's **Signals for next month** only. Each item: before → after · why · the
evidence window. At most about 6 changes; "no changes this month" is a valid outcome, say so when nothing asks.

| Signal | What you may propose |
|---|---|
| the block ends (an easy week or a rebuild week) | re-issue the program for the next block (same answers = same program, new week) |
| a row the weekly loop wants swapped, or a lift stalled 2+ weeks | a swap within its slot: the report lists the same-slot alternatives |
| Advanced offer (placement) | the athlete chooses; Advanced means top sets, an easy week every 6th week and a priority region |
| a change off band | keep, adjust or revert, the athlete's call |
| hit rate out of band | ask before changing anything (sleep, stress, food) |
| volume below the coaching bands | explain; more sets come with Advanced + a priority or longer sessions, never by hand |
| a temporary program past its end | the `adapt` skill's restore |

Show the program change before asking (`--dry-run` writes nothing):

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/monthly_check_in.py" reissue --dir . --today {today} \
  [--swap FROM_ID=TO_ID]… [--promote] [--why "…"] --dry-run
```

## 6. Ask

Every change needs the athlete's own yes; a spine-loaded lift or a level change needs it by name. Changed answers
("3 days from now on") go to `profile.md` first (the `onboard` question), then the re-issue.

## 7. Apply

Run the same `reissue` line without `--dry-run`. It rebuilds through `program_build.py` (the audit gates it; exit
1 = refused, nothing written: report it, never work around it), keeps week 1's date so easy weeks keep their
count, and writes each change to `plan/changes.md` with its band (a swap: the new lift's estimated best single not
lower in 4 weeks; Advanced: targets met 70–85 %). Pain or a temporary constraint goes through the `adapt` skill
instead. If next week's targets were already applied by the weekly review, draft them again from the new
program and apply them with the athlete's OK (new exercises find their weight in their first session):
`progression.py propose --dir . --week {next} --force`, then `apply … --force`. Then refresh the roadmap tables
if there is one: `roadmap.py show --dir . --today {today}`.

## 8. Write and log

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/monthly_check_in.py" report --dir . --today {today} --write \
  [--decision "Swap Romanian Deadlift → Stiff-Legged Dumbbell Deadlift (c3)"]… [--note "the athlete's words"]…
```

It writes `check-ins/{today}-monthly.md` (the report, the athlete's notes verbatim, the decisions or "No changes
this month."), records the due grades in `plan/changes.md` and logs
`- {today} · monthly-check-in · <weeks>: hit rate x %, n change(s) graded, m decision(s)`. Add the nutrition and
physique sections to the file if they ran.

## Never

- Change the program by hand, add sets by hand, or apply anything the athlete did not OK.
- Call a muscle under-trained from direct sets alone, or fatigue from one signal.
- Talk about calories or photos when those skills are off.
