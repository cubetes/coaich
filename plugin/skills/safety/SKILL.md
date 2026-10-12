---
name: safety
description: Medical gate and red-flag pain rule for strength training. Use before building or changing a program or targets, during onboarding health questions, and whenever the user mentions pain, an injury, a new health condition, pregnancy, surgery, chest pain or fainting.
---

# Safety

The gate every coaching skill passes first. It decides **go**, **warn** or **stop** from the athlete's own answers,
shows the exact wording below, and records the result in `coaich.md`. It never diagnoses and never overrides a stop.

> All user-facing wording here is a draft: **lawyer review pending**. Use it word for word; do not soften,
> paraphrase or add medical advice of your own. Spanish wording (`language: es`): [copy-es.md](copy-es.md).

## Gate check (any skill, before a program, targets or a plan change)

Read the front matter of `coaich.md` (find the folder with
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" find`).

- No `safety_acknowledged` date → run **Intake** below first.
- `safety_status: stop` → do not build, change or progress anything. Say why in one line (the stop wording) and
  offer the clearance step. Questions about training in general can still be answered.
- `warn` → go on, and repeat each warning line at the top of whatever you produce.
- `go` → go on.
- Any exercise that loads a `pain` area with `red_flag: true` and no `checked` date stays out of every plan.

## Intake (called by `onboard`, or when the gate finds no acknowledgement)

Ask one step at a time. Read `age_band` from `profile.md` (onboard asks it just before).

**1. Age.** `under-16` → say *"CoAIch is for ages 16 and over."* Set `stop` with reason `age`, log, end. Nothing
else is asked or built. `16-17` → say *"You're under 18: train with a qualified coach or an experienced adult who
can watch your technique."* and add reason `age-16-17` (a warning).

**2. Acknowledgement.** Say exactly:

> CoAIch does not replace a doctor. If you have a condition, an injury or any doubt about your health, see one
> before you train. Reply "I understand" to go on.

Only an explicit yes counts. No yes → `stop`, reason `no-acknowledgement`; nothing is built. Record today's date
and that sentence (without the last one) as `safety_acknowledged` / `safety_acknowledgement`.

**3. Health items.** Ask *"Do any of these apply to you? Reply with the numbers, or 'none'."* and show the list:

| # | id | Wording | Kind |
|---|---|---|---|
| 1 | `pregnancy` | I'm pregnant, or I gave birth less than 3 months ago | stop |
| 2 | `heart` | A doctor has told me I have a heart or circulation condition | stop |
| 3 | `chest-pain` | I've had chest pain, at rest or during exercise, in the last month | stop |
| 4 | `fainting` | I've lost my balance from dizziness, or fainted, in the last year | stop |
| 5 | `doctor-said-no` | A doctor has told me not to exercise, or only under supervision | stop |
| 6 | `surgery` | I've had an operation in the last 6 months | stop |
| 7 | `other` | I have another health reason not to do strength training | stop |
| 8 | `high-blood-pressure` | I have high blood pressure (with or without medication) | warning |
| 9 | `osteoporosis` | I have osteoporosis | warning |
| 10 | `hernia` | I have a hernia | warning |
| 11 | `joint` | I have a bone or joint problem that gets worse with exercise | warning |
| 12 | `leaking` | I leak urine when I strain, cough or jump | warning |

Write the chosen ids to `health_items` in `profile.md`. Do not ask follow-up medical questions.

- **Any stop item** → say: *"From your answers, you need a doctor to tell you that you can do strength training
  before you start. Once you have that, confirm it here."* Then go to **Clearance**.
- **Each warning item** → say: *"You told me: {wording}. Strength training is often part of looking after this,
  but it can change what is safe for you. Talk to your doctor before you start and tell them you plan to lift
  weights. Stop any exercise that makes it worse."* The program is still made.

**4. Pain.** Ask *"Does anything hurt right now when you move? Pick all that apply: none, knee, lower back,
shoulder, elbow or wrist, hip, somewhere else."* For each area: *"Is it strong, sharp, recent, swollen or
spreading?"* Write `pain: [{area, red_flag, checked}]` to `profile.md`, then apply **Red-flag pain**.

**5. Record** (below) and log.

## Clearance

Offer, never push: *"When a doctor has cleared you, reply with this sentence:"*
**"I confirm a doctor has cleared me to do strength training."**

Only that confirmation counts (the sentence, or a clear yes to it). Record today's date and the sentence. One
clearance lifts every stop item answered in this onboarding. A new onboarding (`/onboard` redo) clears it and
asks again, and so does a stop item reported later (step 3 rerun). Do not judge whether a condition is "really"
serious, and do not suggest the user can skip this.

## Red-flag pain (intake and any time later)

- **Red flag** (strong, sharp, recent, swollen or spreading) → say: *"That pain should be checked by a
  physiotherapist or doctor before you load the area. Until then we leave out the exercises that load it. Once
  it's been checked, tell me and I'll add them back."* Set `red_flag: true`. When the user says it was checked,
  set `checked` to today's date.
- **No red flag** → say: *"We'll train around it and pick exercises that don't hurt. If an exercise hurts, stop
  it and tell me. If the pain gets worse, see a physiotherapist or doctor."*
- **Chest pain, fainting or severe breathlessness during exercise**, at any time → say: *"Stop training now.
  Chest pain, fainting or severe shortness of breath can be serious: call your local emergency number or get
  medical help right away."* Then add the matching stop item, blank the clearance and set `stop` until a new
  one.
- A new pregnancy, operation, diagnosis or a doctor's "no" mentioned later → rerun step 3 for that item.

## Record

Update the front matter of `coaich.md`:

- `safety_status`: `stop` if age is under 16, there is no acknowledgement, or there is a stop item and no
  clearance; otherwise `warn` if there is any warning item, `age-16-17` or any pain area; otherwise `go`.
- `safety_reasons`: the ids behind the status (`red-flag:<area>` for red-flag pain).
- `safety_clearance_date`, `safety_clearance_sentence` (blank them when a stop item is added later).

Then: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" log safety "status <status>; <reasons>"`.

## Nutrition safeguards

Calorie targets have their own gate (18+, the eating-disorder answer, `wellbeing_pause`, pregnancy, BMI 18.5,
the resting-energy floor, the loss cap by body fat), enforced by `scripts/nutrition.py`: see the `nutrition`
skill. A pregnancy reported later also switches calorie targets off.

## Never

- Diagnose, name a likely cause, or suggest treatment, medicine or dosing.
- Say "you'll be fine", or that training will fix a condition.
- Build, change or progress a plan while the status is `stop`, whatever the user says.
- Store more health detail than the item ids, pain areas and the dates above.
