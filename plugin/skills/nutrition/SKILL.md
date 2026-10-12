---
name: nutrition
description: Experimental (off unless switched on in coaich.md). Daily calories, protein, fat and carbs, a simple day of meals from the athlete's food preferences and allergies, and corrections from the weight trend. Use when the athlete asks what or how much to eat, wants macros or a meal plan, wants to lose, keep or gain weight, or at a check-in when the weight trend should correct the calories. Also look up foods.
---

# Nutrition

One script does every number: `${CLAUDE_PLUGIN_ROOT}/scripts/nutrition.py`. Never work out calories, macros,
portions, a rate, a body-fat midpoint or a unit conversion yourself; copy what it prints. Rules and evidence:
[references/nutrition.md](../../references/nutrition.md). Spanish wording (`language: es`): [copy-es.md](copy-es.md).

> All safeguard wording is a draft: **lawyer review pending**. Say it word for word. CoAIch gives general
> wellness information: no medical claims, no diagnosis, no supplement or drug dosing.

Run from the athlete folder. `<dir>` is `.` there.

## 1. Answers first

Read the nutrition block of `profile.md` (fields: `docs/athlete-folder.md`). If it is empty, run the questions of
`onboard` step 8a (the eating-disorder question comes before any number). The script names any missing answer
(exit 2): ask that one question, write the answer, run again.

## 2. Targets and a day of meals

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/nutrition.py" plan --dir . [--phase lose] [--rate 0.7] [--meals 3|4|5] \
  [--prefer tofu,quinoa] [--exclude pasta]
```

It writes `plan/nutrition.md` (targets, how each number was made, safeguards applied, a day of meals), the
nutrition block of `plan/CURRENT.md` and the log line. Show the targets line, then any "Safeguards applied"
lines, then the meals. Use `--dry-run` to show a change before writing it, and write only after the athlete says
yes.

- **Swaps.** The athlete wants another food: `--prefer <id>` (ids from `foods`), or `--exclude`. Lasting
  dislikes go in `foods_avoid`; allergies in `allergies`. Never hand-edit amounts in `nutrition.md`.
- **Off target.** The plan says "off target" (calories beyond ±5 % or protein under 95 %): try one other
  `--prefer`, else show it as it is and say which meal to adjust.
- **A packaged food** not in the table: the athlete can read the label to you. Open Food Facts may be fetched for
  that one product only if the athlete asks; never save its data into the plugin.

## 3. Adjust from the weight trend (weekly or monthly)

Only with `weight_tracking: yes`.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/nutrition.py" trend --dir .
```

It prints the trend since the plan came into force and the measured maintenance when the data is good enough
(14+ days, 8+ weigh-ins, tight enough). Ask *"Did you mostly eat to the plan?"* If not, ask roughly what they
ate and pass `--intake <kcal>`, or skip the correction. If they agree, run `plan` again: it uses the measured
maintenance and the same phase. A trend faster than the loss cap always means **eat more**; say so.

## 4. Safeguards (the script enforces them; you say the words)

Exit 3 means a safeguard. Say the printed wording exactly, add nothing, and do not argue or look for a way round.

| Code | When | What happens |
|---|---|---|
| `experimental-off` | `experimental` in `coaich.md` is not `on` | no targets; `nutrition.md` says off. Say the wording, then ask *"Switch it on?"*; a yes sets `experimental: on` in the front matter of `coaich.md`, then run again (the other safeguards still apply) |
| `age` | under 18 | no targets; `nutrition.md` says off |
| `eating-disorder` | `eating_disorder_history` is anything but `no` | no calorie targets, no fat-loss phase; points to professional help |
| `wellbeing-pause` | `wellbeing_pause` has a date | same, plus no photo reviews (physique skill) |
| `pregnancy` | `pregnancy` in `health_items` | no calorie targets; doctor or midwife |
| `bmi` | losing with BMI under 18.5 | refused; the plan in force stays; offer maintain or gain |
| `consent` | `trend` with `weight_tracking: no` | no trend |

The resting-energy floor and the loss cap by body fat apply on their own and show under "Safeguards applied".

**Wellbeing pause.** If, at any time, the athlete describes very low eating, skipping meals to make up for food,
making themselves sick, laxatives, fear or guilt around food, or distress about their body: set
`wellbeing_pause: <today>` in `profile.md`, run `plan` (it switches targets off and prints the wording), and say
it. Do not diagnose or ask follow-up questions. Lift it only when the athlete asks in their own words: blank the
field and add `- <today>: wellbeing pause lifted at the athlete's request.` under `# Profile`. The physique skill
(and the roadmap's cut and bulk phases) read the same flag: one shared gate, `athlete_folder.py gate`.

**Never:** targets for someone under 18; calories under resting needs; a faster loss than the cap; fat loss
below BMI 18.5; meal-skipping, fasting protocols, detoxes or "cleanses"; supplement, drug or medical advice;
comments on how anyone's body looks.

## 5. Look up foods

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/nutrition.py" foods "chicken" [--diet vegan] [--avoid gluten,soy] [--group protein]
```

Per 100 g, with the USDA FoodData Central id for each food.
