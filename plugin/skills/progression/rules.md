# Progression rules

The rules `scripts/progression.py` runs. The code is the authority. This file explains it.

## The loop

```
grade    last week's frozen targets vs data/sets.csv   → grades written into targets_{last}.json
propose  next week's targets (status "proposed")        → targets_{next}.json + Markdown table
         the athlete confirms; every "ask" row needs an explicit OK
apply    accepted rows → targets_{next}.json "applied"  (frozen; nothing else is written)
```

- **One row per routine × exercise.** The same exercise in two routines is two rows with two
  targets. Row id = `{routine-slug}-{slot}` (`upper-a-1`).
- **Frozen once applied.** A targets file is a pre-registration. `propose` refuses to rewrite an
  applied or graded week (`--force` only to redo a mistake). Grading adds fields. It never changes
  the target.
- **Offline.** No network. Pushing targets to an app (Hevy) is a separate, optional step.

## What the engine reads from `plan/program.json`

Per exercise (`routines[].exercises[]`). Everything except the id is optional.

| Field | Meaning | Default when missing |
|---|---|---|
| `exercise_id` (or `id`) | free-exercise-db id; sets.csv rows match on it | required |
| `name` | display name | the id with spaces |
| `sets` | a count (`3`: weights still to find) or `[{weight_kg, reps, type}]` (`weight_kg: null` = find it) | — |
| `rep_range` `[lo, hi]` | double-progression range | from the sets' reps |
| `reps_left` `[lo, hi]` | target reps left on working sets | spine `[2,2]` · compound `[1,2]` · isolation `[0,2]` |
| `load_step_kg` | one load increment | by `tool`: barbell 2.5 · dumbbell 2 · machine 5 · bodyweight 0 |
| `tool` | `barbell_lower`, `barbell_upper`, `dumbbell`, `machine`, `bodyweight` | from the id words |
| `category` | `spine` (load increases need the athlete's OK) · `compound` · `isolation` | `barbell_lower` → spine; curl/raise/fly… → isolation; else compound |
| `assisted` | `weight_kg` is assistance: progression runs inverted | false |
| `overload` | `false` takes the row out of the loop | true |
| `history_ids` | older exercise ids whose history counts for this slot | [] |

Top level: `level` (`beginner|intermediate|advanced`, caps the jump; default intermediate),
`start` (date) + `easy_weeks` (1-based program week numbers). Inferred fields are flagged
`inferred:<field>` on the row. Program-build should write `category` and `tool` explicitly.

## Week types

`full · moderated · recovery (easy week) · travel`, from the `plan/CURRENT.md` calendar
(`| W<n> | type | start date | …`), else `program.json` `easy_weeks`, else full. `--week-type`
overrides. A week whose first session follows ≥ 14 days off is graded as `reentry`: not graded, but what was
lifted that week sets the next target (below).

## Grading

- **Exposure** = the routine's session in that ISO week (Mon–Sun), matched by `workout_name`;
  done twice → the last one.
- **Working sets** = `normal` + `failure`. Warm-ups and drop sets never count. Only the **N
  heaviest** working sets are graded (N = target sets), so ramp sets logged as normal fall out.
- Logged sets are paired with target sets to maximise sets met.
- A set **meets** its target at ≥ target load and ≥ target reps, or at a heavier load with
  ≥ `rep_lo` reps and an Epley estimate ≥ the target's.

| Grade | Rule |
|---|---|
| `hit` (met) | every target set met |
| `partial` (close) | no set missing, every load within one step, ≤ 2 reps short in total |
| `miss` (missed) | anything worse |
| `not_done` | session not logged, or the exercise not in it |
| `excluded` (skipped) | easy/travel/re-entry week, `overload: false`, a level shift (top load > 25 % or 3 steps off target: another machine or variant), or the first session of a row with no weight yet (`calibration`) |

Grade flags: `exact_copy` (logged = target exactly; a pre-filled value saved untouched?),
`overshoot`, `failure_used`, `level_shift`, `calibration`, `rep_pr`, `athlete_note`.

**Rep PR.** A miss that beats the previous graded exposure: top load ≥ previous AND (best set at
that load +≥ 2 reps, OR total reps +≥ max(2, ⌈5 %⌉) with the best set not lower). The grade stays
`miss`; the streak counts it once and stops looking back, so it saves one week.

**Athlete notes.** A set's `note` rides beside the grade as `athlete_note`. It never changes a
grade, a target or a decision.

## Decisions

Evaluated per row from last week's grade and the row's history (newest first). Reason codes in
brackets; sentences in `TEXT` in the script.

| Situation | Decision | Next target | Needs OK |
|---|---|---|---|
| Next week is an easy week | `easy_week` [easy_week] | −10 % load (≥ 1 step), −⅓ sets; the old target is stored | no |
| Week after an easy week | hold [after_easy_week] | the stored target returns | no |
| Next week is travel | hold [travel_week] | frozen | no |
| Not done | hold [not_done]; 2 weeks → [not_done_x2] | carried | no |
| No weight yet, first session logged | hold [calibrated] | the heaviest N logged sets, reps capped at `hi`, −1 rep on a failure set | no |
| First week back after ≥ 14 days off, logged | hold [reentry_start] | the heaviest N logged sets as in calibration, each capped at the target from before the break (a heavier set takes the old target) | if any load is lower |
| Other excluded | hold [excluded_hold] | carried; level shift → `coach_review` | no |
| 2nd level shift in a row | hold [reanchor] | re-anchored to the logged sets | **yes** |
| `partial` | hold [close_hold] | repeat | no |
| 1st miss / rep-PR miss | hold [miss_hold] / [rep_pr_hold] | repeat | no |
| 2nd miss in a row | hold [miss2_hold] + `coach_review` | repeat once more | no |
| 3rd miss in a row | `reduce` [reduce] | the (load, reps) pair on the grid (1 step down to −20 %, reps in range) whose Epley estimate is closest to **92 %** of the best logged set, never above **95 %**; tie → heavier; best set over 12 reps → the sentence says it is a rough guide (Epley drifts at high reps). Assisted: +5 % assistance [reduce_assisted]. Bodyweight: reps to `lo` [fewer_reps] | **yes** |
| ≥ 3 misses after an accepted reduce | `swap` [swap_after_reduce] | proposal only | **yes** |
| Met, compound set with 0 reps left | hold [failure_hold] | same; stop a rep earlier | no |
| Met, every set at `hi`, reps left below target | hold [top_too_hard]; the 2nd week in a row +1 step [step_despite_hard] | | spine: yes |
| Met, every set at `hi` | `increase` [step] | + the jump table below, reps → `lo`. Assisted: −1 step of assistance [step_assisted]; none left → `swap` [swap_no_assistance]. Bodyweight: hold [top_no_load] | **spine: yes** |
| Met, below `hi` | hold [add_rep] / [reps_to_done] | reps → what was done (≤ `hi`); unchanged → +1 rep on the first set below `hi`. Sets logged ≥ 1 step heavier move to that load [reanchored] | spine, if the load rises |

- Miss streaks skip `not_done`, `excluded` and moderated weeks. An accepted reduce starts the count again:
  the misses before the lighter block don't count against it.
- Moderated weeks trim one set; the next full week restores the program's set count.

## The jump table (G119)

Reps left on the hardest graded set, against the row's `reps_left` target `[lo, hi]`:

| Reps left | Steps |
|---|---|
| 0 on a compound | 0 (failure hold) |
| below `lo` | 0 (hold; the 2nd week in a row: 1) |
| `lo`…`hi`, or not logged | 1 |
| `hi` + 1 | 2 |
| ≥ `hi` + 2 | 3 |

Caps: steps by level (beginner 3 · intermediate 2 · advanced 2), then kg by equipment (lower-body
barbell 10 kg · upper-body barbell 5 kg · others 2 steps). The table is `JUMP_STEPS`, `MAX_STEPS`,
`JUMP_CAP_KG` at the top of the script; setting every step to 1 gives classic one-step double
progression.

## Shared test cases

[`tests/fixtures/target_cases.json`](../../tests/fixtures/target_cases.json): one case per rule above, each a
program row, the sets logged week by week (athlete-folder format 1) and the expected grade, decision, reason
code, next sets and OK for every proposed week. `tests/test_target_cases.py` runs them through this engine. An
app's engine copies these rules (ADR 0006) and passes when it gives the same answers. A deliberate rule change
refills them with `python3 tests/test_target_cases.py --write`; review the diff.

## Change nothing + evidence rules

- "No changes this week" is a valid outcome. The engine's hold is a decision, not a gap to fill.
- **Minimum evidence** for a coach change (override, swap, set change) on top of the engine: the
  slot has ≥ 3 sessions of history and ≥ 1 full week since its last change, and ≥ 2 stalls (miss,
  close, or no rep progress) or the athlete's own note about it.
- **At most 6 coach changes per review** (`apply` refuses more overrides). Rank by evidence; the
  rest hold and are named as held.
- Every change states before → after, why, and the evidence window.
- Spine-loaded lift increases always need the athlete's explicit OK, including an override.

## Apply

```
progression.py apply --dir . --week 2030-W11 --accept-all --approve lower-a-1 \
    --override "upper-a-2=60x10·10·9:shoulder sore, same weight" --reject upper-b-4
progression.py apply --dir . --week 2030-W11 --auto-isolation-only     # check-in skipped
```

- `--accept-all` accepts every row that needs no OK; "ask" rows only when listed in `--approve`.
  Unconfirmed rows stay at last week's target.
- `--override ID=KGxR·R·R:reason`: the reason is mandatory; kg 0–400, reps 1–30, ≤ 10 sets; a
  spine row's load above last week's is refused unless the id is in `--approve`. Any failure aborts
  before anything is written.
- `--auto-isolation-only`: isolation rows that need no OK (and easy-week rows) apply; compound and
  spine rows hold. It cannot approve or override.

## Guards

- **Stale data.** `grade`/`propose` refuse when the data runs out before the Sunday of the graded
  week. Data-through = `--data-through` (the athlete says the week is complete) > the latest
  `· import ·` line in `log.md` > the newest set date.
- **Regrade.** `grade` on a graded week needs `--force`, and is refused once the next week is
  applied. Write the correction in the check-in instead.

## Hit-rate band

No verdict before 4 graded weeks. Then the rolling 4-week hit rate (met ÷ graded) is judged against
**70–85 %**: above = targets too easy (or pre-filled values saved untouched: check `exact_copy`);
below = too demanding or a recovery problem (want ≥ 2 converging signals before calling fatigue).

## Evidence

- Double progression inside a rep range: practitioner consensus (low evidence); load progression
  drives strength gains (Schoenfeld et al. 2017); rep ranges (Grgic et al. 2018).
- Reps left as the effort check (Zourdos et al. 2016); proximity to failure and hypertrophy
  (Refalo et al. 2024; Robinson et al. 2024). Reps-left autoregulation ≥ fixed loading (Zhang et
  al. 2021 SR/MA); reps-left estimates work in novices, about one rep low (Halperin et al. 2022).
  The step counts and caps are our rule.
- Easy weeks (reduced volume and load): Coleman et al. 2024 (RCT); Bell et al. 2023 (Delphi) for
  the interval.
- 92 % reduce: no study tests how much to cut after a stall. Published autoregulation steps are
  2–5 % (Helms 2018); 1RM day-to-day noise ~4 % (Grgic 2020); 92 % ≈ 3 reps left. Rep-PR margins
  sit above the 0.7–1.9 rep/set typical error (Mitter 2022; Hernández-Belmonte 2022).
- Hit-rate band and the 3-miss rule: panel decision (low evidence). 0.6: one more try before lighter (was 2
  misses), since both rules are practitioner and repeating the load first is the gentler one.
