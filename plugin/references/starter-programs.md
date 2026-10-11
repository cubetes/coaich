# Starter programs

How `scripts/program_build.py` turns intake answers into a program. Same rules as the CoAIch app's Release 1
core; `tests/test_program_parity.py` checks both give the same program for every answer. Every template is our
own: no third-party program name, table or text. Evidence and grades: [evidence.md](evidence.md). "Our rule" =
a practitioner number, no study behind the exact value.

The exact days (exercises, sets, order per time version) live in one place: `days_of()` in
`program_build.py`. To see one, run `program_build.py --dir <folder> --dry-run`.

## Grid

Level × days asked → layout. Every cell has a program (the test `test_no_answer_combination_is_a_gap`).

| Days asked | Beginner | Intermediate / advanced | 60+ |
|---|---|---|---|
| 2 | `fb2b` full body | `fb2i` full body | same |
| 3 | `fb3b` full body A/B over 3 days | `fb3i` 3 different full-body days | same |
| 4 | `ul4b` upper/lower | `ul4i` upper/lower | same |
| 5 | `ul4b` + "4 days at most for 12 weeks" | `ulf5i` upper/lower + full body | beginner `fb3b`, trained `ul4i` |
| 6 | `ul4b` + the same line | `ppl6i` push/pull/legs | as 5 |

Days outside 2–6 are clamped. Time answer → version: 30 = four exercises as two antagonist pairs (≤ 28 min) ·
45 = the first four or five · 60 = the full day · 75 = full + an arm or core add-on (not beginners). The time is
a hard cap: every session ≤ the answer (8 min warm-up + 3.25 min per compound set + 2 min per isolation or
paired set; our rule).

## Slots

| Code | Slot | Usual pick → alternatives |
|---|---|---|
| SQ | squat | barbell squat → goblet squat, hack squat, front squat |
| SM | machine squat | leg press → hack squat |
| HI | hinge | Romanian deadlift → stiff-legged DB deadlift, hip thrust, deadlift |
| LU | lunge | DB split squat → step-ups |
| KE / KF | knee extension / flexion | leg extension / lying → seated leg curl |
| HP / VP | horizontal / vertical press | barbell bench → DB bench, machine, incline DB / standing press → DB, machine |
| FL | fly | cable fly → DB fly, incline DB fly |
| HR / VR | row / vertical pull | cable row → iso row, barbell row / wide pulldown → close-grip, pull-ups |
| LR / RD | lateral / rear delt | lateral raise → cable / face pull → reverse machine fly, cable rear fly |
| CU / TE | curl / triceps | DB curl → … / overhead cable extension → pushdown |
| CA / CO | calves / core | standing → seated calf raise / dead bug, plank, cable crunch, leg raises |

Beginners never see the barbell row, pull-ups, weighted pull-ups, deadlift or front squat as alternatives. The
same exercise never appears twice in a day; ≤ 7 exercises a day.

**Spine set** (axial load standing, a loaded hinge or a loaded lunge): barbell, front, box and hack squat, leg
press, DB squats, lunges, split squats, step-ups, Romanian, stiff-legged, single-leg, conventional and trap-bar
deadlifts, good morning, standing military press, bent-over barbell row. Never below 2 reps in reserve; never
in a low-back program.

## Prescription

| | Beginner | Intermediate | Advanced |
|---|---|---|---|
| Sets per exercise | 2 in weeks 1–4, then 3 (our rule) | 3–4 | 3–4 (+2 on two priority slots) |
| Main lift reps | 8–12 | 6–10; strength goal 4–6 | same + one top set |
| Other compounds | 8–12 (accessory/light 10–15) | 8–12 | 8–12 |
| Isolation | 12–20 | 10–20 | 10–20 |
| Reps in reserve | 2–3 → 1–2 from week 5 | main 2, others 1–2, isolation 0–2 | main 1–2, others 1–2, isolation 0–2 |
| Easy week | triggered only | every 7th week | every 6th week |

Spine lifts and, with the leak item, squat and hinge: ≥ 2 in reserve. 60+: ≥ 8 reps everywhere, 2 sets and 3 in
reserve on compounds for 8 weeks, "lift briskly, lower slowly". Rest: main lift, squat and hinge 180 s, other
compounds 120 s, isolation 75 s, 60 s between the halves of a pair. Bodyweight ladders: pulls 6–12, pushes and
core 8–15. Strength goal: the main hinge becomes the deadlift, 3 sets.

Easy week (counted in sessions done, `days` sessions = a week): a third fewer sets, about 10 % lighter, 3–4 in
reserve, nothing graded, never a week off. The program is rebuilt when the prescription changes
(`rebuild_at_week`: 5 for beginners, 9 for 60+).

## Modifiers

| Answer | Effect | Rule |
|---|---|---|
| Goal (intermediate, advanced) | strength → main lift 4–6, hinge = deadlift; muscle/both → 6–10 | row 28 |
| Advanced | main lifts start with a top set; bench top set only with safety bars or a spotter, else dumbbells | rows 29, 43 |
| Priority (advanced, one region) | +2 sets on two of its slots (≤ 4 each), −1 set on two other isolations, its slot right after the main lift; never over the minutes, under a floor or over MRV; 5 days → day 5 is its day | row 29 |
| Age 16–17 | "Train with an adult who knows the lifts." | row 4 |
| Age 60+ | ≤ 3 days (beginner) or ≤ 4 (trained); chair-stand screen failed → squat starts at the chair squat | row 44 |
| Leak item | squat and hinge ≥ 2 in reserve + breathing line + pelvic-floor physio pointer | row 3 |
| Returning (gap > 3 months) | placed one level down, early level check (week 4 or 6) | row 12 |

## Pain

| Area | Swaps (no red flag) |
|---|---|
| Lower back | every spine exercise: squat → goblet squat, hinge and leg curl → hip thrust, leg press → leg extension, lunge → bodyweight walking lunge, barbell row → iso row, standing press → seated DB press; others dropped |
| Shoulder | benches → neutral-grip DB bench, standing press → machine press, pulldowns → close-grip, no flyes |
| Knee | squat → leg press, lunge → hip thrust, no leg extension |
| Hip | squat → leg press, hinge → glute bridge, no lunge |
| Elbow or wrist | barbell benches → neutral-grip DB, standing press → DB press, curls → hammer curls, pull-ups → close-grip pulldown |
| Somewhere else | nothing changes; the warnings still show |

A red flag ("strong, sharp, recent, swollen or spreading") not yet checked leaves out every slot that loads the
area (knee SQ SM LU KE · low back and hip SQ SM HI LU, and every spine exercise for the low back · shoulder HP VP
FL LR VR · elbow or wrist CU TE) until a physio or doctor has checked it. Two areas: both apply; an exercise one
area allows and the other forbids is left out. With pain, the volume floors (G1) and frequency (G3) are not
gates: exercises are left out on purpose.

## Rules

`rules_fired` in `program.json` names these ids (the app's Release 1 decision table numbering).

| Id | Rule |
|---|---|
| row 2 | serious health item: no program until a doctor's clearance is confirmed (exact sentence) |
| row 3 | leak path |
| row 4 | under 16: no program; 16–17: supervision line |
| rows 5–8 | pain areas, red flags, swaps |
| §3.2 placement rows 1–8 | level from history × last trained (× known squat and bench loads for advanced) |
| row 12 | returning lifter |
| row 14 | layout by level × days, with the day caps |
| row 15 | time version |
| row 28 | goal |
| rows 29, 43 | advanced: priority and top sets |
| row 44 | 60+ |
| G120 | strong medical warning (high blood pressure, osteoporosis or hernia): program + "talk to your doctor" (no diabetes item: G120 D10) |

## Placement

| History (2+ sessions a week) | Last trained | Squat + bench loads known | Level | Returning | Check |
|---|---|---|---|---|---|
| never / under 6 months | — | — | beginner | | |
| 6 months – 2 years | last 3 months | — | intermediate | | |
| 6 months – 2 years | 3–12 months | — | beginner | yes | promotion week 4 |
| 6 months – 2 years | over a year | — | beginner | yes | promotion week 6 |
| over 2 years | last 3 months | yes | advanced | | |
| over 2 years | last 3 months | no | intermediate | | advanced week 6 |
| over 2 years | 3–12 months | — | intermediate | yes | advanced week 6 |
| over 2 years | over a year | — | beginner | yes | promotion week 4 |

Every ambiguous answer goes down a level (wrong placement upward is the dangerous direction). Thresholds: our
rule. Promotion is always a prompt the athlete confirms.
