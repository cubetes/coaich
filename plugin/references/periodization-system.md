# Periodization vocabulary

One vocabulary for training periods, on one axis: **scale**. Every skill and file uses these words.

## The four tiers

`macrocycle ⊃ phase ⊃ mesocycle ⊃ microcycle`

| Tier | Scale | What it is | Where it lives |
|---|---|---|---|
| **Macrocycle** | years | the long-term goal and direction; prescribes nothing | `plan/roadmap.md` |
| **Phase** | months | the direction of energy balance: **cut**, **bulk** or **maintenance** | `plan/roadmap.md`, `plan/CURRENT.md` |
| **Mesocycle** | 4–7 weeks | one program block: the exercises, sets and rep ranges in `plan/program.json` | `plan/program.json` |
| **Microcycle** | 1 week | the week you actually run: one pass through the program's sessions | `plan/targets/targets_YYYY-Www.json` |

A new program inside the same phase is a new **mesocycle**, not a new phase.

## Week types (a flavour of the week, not a tier)

| Type | Changes | Effect |
|---|---|---|
| **Full** | — | the program as written (the default) |
| **Easy week** (a deload) | training | a third fewer sets, about 10 % lighter, 3–4 reps in reserve, nothing graded; never a week off |
| **Diet break** | nutrition | calories back to maintenance for a week (v0.2) |

Easy weeks and diet breaks are independent: they need not fall in the same week. A week type overrides the
phase default for that week only. Easy weeks: beginners none planned (triggered by stalls or joint pain),
intermediate every 7th week, advanced every 6th, counted in sessions done, not calendar weeks (our rule; the
shape has RCT support, see [evidence.md](evidence.md)). `program.json` lists them in `easy_weeks`.

## Review cadence (laid over the plan, not a tier)

| Cadence | Reviews | Skill |
|---|---|---|
| weekly | the microcycle: grade it, set next week's targets | `weekly-review` |
| monthly | the mesocycle: progress, did the changes work, next block | `monthly-check-in` (v0.2) |
| end of phase | closes a cut or bulk | `monthly-check-in` |

## Writing rules

- Write **macrocycle** in full; "macro" means macronutrients.
- **Phase** means energy-balance direction only. It is never an easy week, and never a duration word.
- Keep "long/short term" and "weekly/monthly" out of the tier names.
- Injury "phases" belong to the physio, not to this plugin: CoAIch never classifies an injury.

Evidence: periodized training beats non-periodized for strength, not for size; undulating beats linear for 1RM in
trained lifters only (Moesgaard 2022, SR/MA; Williams 2017; Rhea 2002). The tier names are organisational.
