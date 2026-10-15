# Muscle-group rubric

How the `physique` skill rates progress photos and turns the ratings into training priorities.
`scripts/photos.py` holds the same ids, tiers and matrix; a test keeps the regions in step with `program_build.py`.

**What this is.** A practical coaching convention for looking at your own photos the same way every time. It is
not a validated measurement and not a medical assessment. It rates how developed a muscle group looks
*compared with the rest of your own body*, never against other people, and never how attractive anyone looks.

## The 12 groups

| id | Group | Seen best from | Visual impact | Program priority (`priority` in `profile.md`) |
|---|---|---|---|---|
| `calves` | Calves | side, back | high | `calves` |
| `quads` | Front of the thighs | front, side | medium | `quads` |
| `hamstrings` | Back of the thighs | side, back | low | `glutes-hamstrings` |
| `glutes` | Glutes | side, back | low | `glutes-hamstrings` |
| `lats` | Lats (back width) | back, front | high | `back` |
| `upper-back` | Mid and upper back (thickness) | back | medium | `back` |
| `traps` | Traps | back, front | medium | `back` |
| `chest` | Chest overall | front, side | medium | `chest` |
| `upper-chest` | Upper chest | front | medium | `chest` |
| `front-side-delts` | Front and side shoulders | front | high | `shoulders` |
| `rear-delts` | Rear shoulders | back | high | `shoulders` |
| `arms` | Arms (biceps and triceps) | front, side, back | high | `arms` |

Abs, waist and posture are not rated. Posture is a later version (see the physique skill).

## What to look at, by pose

| Pose | Look at |
|---|---|
| Front, relaxed | Upper chest, shoulder width and roundness, biceps, front of the thighs (outer sweep and the inner muscle above the knee), the width of the back showing past the waist |
| Side, relaxed | How far the chest stands out, the back of the upper arm, glutes, back of the thighs, calves |
| Back, relaxed | Back width and where the lats end, rear shoulders, mid-back thickness, the line from glutes to hamstrings, calves |

## Ratings (4 tiers)

| id | Means |
|---|---|
| `strong` | Ahead of the rest of the body for this person's training age. Keep it as it is. |
| `adequate` | In proportion with the rest of the body. Keep it as it is. |
| `lagging` | Visibly behind the rest of the body. |
| `severely-lagging` | Far behind; the clearest imbalance in the set. |

Rate in neutral words. Describe size and shape of muscle groups only: "the calves look small next to the
thighs", never words about attractiveness, flaws, ugliness or fat as a fault.

**Confidence** for a set: `high` (same light, same place, same time of day, all three poses, relaxed),
`medium` (one of those differs) or `low` (two or more differ, a pose is missing, or a pump or tan changes the
look). A change is only called a change when both sets are at least `medium`.

## Visual impact

How much a group changes the outline of the body when it grows. Our rule (practitioner judgement, low evidence):
`high` for calves, lats, shoulders and arms; `medium` for chest, front of the thighs, mid-back and traps; `low`
for glutes and back of the thighs, which clothes and the side view hide.

## Priority (rating × visual impact)

| Rating | high | medium | low |
|---|---|---|---|
| severely-lagging | 1 | 1 | 2 |
| lagging | 2 | 2 | 3 |
| adequate | 3 | keep | keep |
| strong | keep | keep | keep |

Ties: priority, then visual impact, then the order of the table above. A group the user's goal physique
stresses counts one tier further behind (an `adequate` group becomes `lagging` for ranking only).

**Into the program.** `program_build.py` gives a priority to **advanced** lifters only, and only one region: the
region of the top-ranked group. For beginners and intermediates the ranked regions become a long-term note in
`profile.md` (`long_term_priorities`): every area gets the same care until the base is built, which is the
fastest route for them anyway.

## Timelines (our rule, not a study)

Rough time before a priority group looks different in photos, with steady training, enough food and sleep:
beginner 8–12 weeks, intermediate 12–20 weeks, advanced 20–36 weeks. Genetics, age, sleep, food and how often
training is missed move this a lot. Say it as a range, never as a promise. Some limits are structural (where a
muscle attaches, frame width) and training does not change them: say so in plain words, as practitioner
judgement.

## Body fat from photos

Allowed only as a **range at least 4 points wide** ("about 15–19 %"), never a single number. Say the
uncertainty every time, in plain words: *"This is a rough visual guess, not a measurement. Light, pump, tan,
time of day and the camera change it. Even a phone-photo method built and tested for this was off by up to
about 5 points for some people (Majmudar et al. 2022, npj Digit Med 5:79,
[doi:10.1038/s41746-022-00628-3](https://doi.org/10.1038/s41746-022-00628-3)); a general look at photos has
not been tested at all."* Never compare it with a scale or scanner reading: different methods give different
numbers. The range goes in `photos/ratings.md`; its midpoint goes in `data/body.csv` with
`source = photo-range`, only on a date with no reading from another source.
