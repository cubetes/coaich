---
name: physique
description: Experimental (off unless switched on in coaich.md). Review progress photos by muscle group, compare them with the last set, give a rough body-fat range, and turn a goal physique into training priorities. Use when the user says "review my progress photos", "compare my photos", "analyse my physique", "ideal physique", "what should I prioritise", or shares progress photos.
---

# Physique

Rates **muscle groups** in the user's own progress photos with one rubric, tracks them over time, and turns a
goal physique into training priorities. Every file write goes through `scripts/photos.py`; the rubric (groups,
ratings, priority matrix, timelines, body-fat rules) is [muscle-rubric.md](../../references/muscle-rubric.md).

> User-facing wording here is a draft: **lawyer review pending**. Use it as written.

`P="${CLAUDE_PLUGIN_ROOT}/scripts/photos.py"`; find the folder with
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" find`.

## 1. Gate (always first)

Run `python3 "$P" gate --dir <folder>` (the shared wellbeing gate, `athlete_folder.gate`). Exit 0 → go on.
Exit 2 → the printed `reasons` decide:

| Reason | Do |
|---|---|
| `experimental-off` | Say *"Photo and physique review is experimental: its safety texts haven't had a legal review yet. It is off unless you switch it on. Switch it on?"* A yes sets `experimental: on` in the front matter of `coaich.md`; gate again (the other reasons still apply). A no: stop. |
| `age`, `age-unanswered` | Say *"Photo and physique reviews are for ages 18 and over."* Unanswered: ask the onboard age question first. Stop. |
| `eating-disorder-history` | Say *"Photo and physique reviews are switched off for you, because of your answer about eating disorders. That keeps the focus on how you train and feel. If you'd like support, an eating-disorder service or your doctor can help."* Stop. Never offer a way around it. |
| `wellbeing-pause` | Say *"Photo reviews are paused, as we agreed. That pause lifts only when you ask for it."* Stop. |
| `eating-disorder-unanswered` | Ask the eating-disorder question from `/onboard` (its exact wording), write the answer to `profile.md`, gate again. |
| `no-photo-opt-in` | Photos: ask the opt-in from `/onboard` step 8; a yes writes `photos_opt_in: yes`. Ideal physique without photos is still allowed (step 6, described ratings). |

Also run the `safety` gate: with `safety_status: stop`, rate photos if asked, but pass nothing to
`program-build`.

**Mid-review stop.** If the user, at any point, says things like fearing food or weight, skipping meals or
making up for eating, hating their body, or wants to look "smaller" at any cost: stop the review, say *"I'll stop
the photo review here. What you said matters more than any rating. Please talk to your doctor or an
eating-disorder service; they can help."*, set `wellbeing_pause: <today>` in `profile.md` (the shared flag:
it also switches calorie targets off, so run the `nutrition` skill's `plan` if nutrition is on) with a dated note
under `# Profile` ("wellbeing pause on <date>, from a photo review"), and log it. Do not resume it yourself; only
the user's own explicit request lifts it (blank the field, add a dated note), as in the nutrition skill.

## 2. Photos in

**Never open an original.** Do not Read, preview or describe any photo the user gives you, and do not run any
other tool on it: the face comes off on the user's computer first, and you look only at the copy in `photos/`.
This holds even if the user asks you to "just look". The only exception is section 6 (a goal picture of someone
else, which is never filed).

Say once per session: *"Before I see a photo, your computer removes your face from it: by default it cuts the
picture just below your chin, so your neck, traps and shoulders stay in. Only that copy is kept, in your folder
(`photos/`, which git ignores), with its location and camera data removed. Your original stays where you have
it, unchanged."*

Pose protocol, the same every time: **front, side, back**, relaxed (not flexed), same light, same place, same
time of day (morning, before eating, is easiest to repeat), camera at chest height about 2–3 m away, tight or
little clothing, head level, only you in the picture. JPEG or PNG; on an iPhone, Settings › Camera › Formats ›
Most Compatible.

**Ask the user which file is which pose** (you cannot look). Then:

```
python3 "$P" file --dir <folder> --date YYYY-MM-DD front=<path> side=<path> back=<path> [--anonymise crop|blur]
```

`--date` = the day the photos were taken (ask if unsure). The face is removed first (Apple Vision on a Mac,
OpenCV on Windows or Linux if installed), then the copy is filed as `photos/DATE/POSE.jpg`. `--anonymise blur`
covers the face, ears and hair with a solid grey block instead of cutting; use it only when the user asks
(`photo_anonymise: blur` in `coaich.md` makes it their default). Exit 2 writes nothing and names the problem:

| Problem | Do |
|---|---|
| no face found, several faces, a face that could not be outlined, a face low in the picture | Say the printed reason. Ask the user to crop the photo themselves just below the chin (or retake it alone, head level). When they say they cropped it, file it again with `--user-cropped`; that passes only if no face is found. |
| chin too close to the shoulders | Ask for a retake with the head level, or a self-crop as above. |
| no face detector on this computer | Say so. A Mac needs Apple's command line tools (`xcode-select --install`); elsewhere `pip install opencv-python` adds one. Or the user crops it and you file with `--user-cropped`. |
| a pose already filed | Ask before adding `--replace`. |
| HEIC | Ask for JPEG. |

A back view is never cut, so raised arms stay: a grey block covers the back of the head instead.

**Then check the filed copies** (`photos/DATE/`), the only images you open. If any part of a face still shows,
delete that file at once (`rm`), say so, and ask the user to crop it themselves. If a pose is not what the user
said (a side photo filed as front), say what you see and re-file the right originals with `--replace`.

Afterwards say: *"Your original photos are still where you had them, with your face and their location data.
You can delete them if you don't need them."* Offer; never push, and never delete them yourself.

## 3. Rate

Read the filed images (`photos/YYYY-MM-DD/`). Rate each of the 12 groups the poses show, with the rubric's four
tiers, plus one confidence for the set (rubric: high / medium / low). Notes: one short neutral line where useful
("left calf a bit smaller than right").

```
python3 "$P" rate --dir <folder> --date YYYY-MM-DD calves=lagging arms=adequate ... --confidence medium \
  [--note calves "left smaller than right"]
```

## 4. Compare with the previous set

`python3 "$P" sets --dir <folder>` lists the dated sets. With two rated dates:
`python3 "$P" compare --dir <folder> [--from D1 --to D2]` → per group `better | same | worse` and the lower
confidence of the two. Call something a change only when that confidence is medium or high; otherwise say the
photos are too different to tell. Never infer the order of sets from anything but their dates.

## 5. Body-fat range (optional, ask first)

Only if the user wants it. Give a range at least 4 points wide, say the rubric's uncertainty paragraph in full,
then:

```
python3 "$P" bodyfat --dir <folder> --date YYYY-MM-DD --low 15 --high 19
```

It writes the range to `photos/ratings.md` and the midpoint to its own `photo-range` row of `data/body.csv` (one
row per date and source: a scale or Apple Health reading the same day stays, and wins wherever one number is
needed). Never compare it with a scale or scanner number, and never turn it into a dated target: goals are
rates (see the `roadmap` skill).

## 6. Goal physique → priorities

The user describes a goal look, or shows a picture. From a picture of someone else: describe only which muscle
groups it stresses (e.g. "wide shoulders, full upper back, big arms"); never name, identify, rate or judge the
person, never file or keep the picture. Write the description to `ideal_physique` in `profile.md`.

Then rank, from the latest rated set or, without photos, from 2–3 questions about how the groups compare
(unanswered groups count as `adequate`):

```
python3 "$P" priorities --dir <folder> [--date D | --rating calves=lagging --rating arms=adequate ...] \
  --emphasis front-side-delts,upper-back,arms
```

It prints the ranked groups, `level`, `priority` (advanced only: one program region), `long_term` and
`timeline_weeks`. Write them to `profile.md`:

- **Advanced:** `priority: <priority>`, the rest to `long_term_priorities`. Offer `program-build` to rebuild with
  it.
- **Beginner or intermediate:** `long_term_priorities: [<regions>]`, `priority` unchanged. Say *"For now every
  area gets the same care: that builds the base fastest. These priorities come into the program once you move
  up to Advanced."*

Timeline, always as a range with its caveats: *"Visible change in a priority group often takes about
{timeline_weeks} weeks of steady training at your level. It may be faster or slower: genetics, sleep, food and
missed sessions all change it. This is a rough guide, not a promise."* Some goals are not reachable for
everyone (frame width, where muscles attach); say so plainly when the gap is structural.

## 7. Report and log

In chat: the rating table (group · rating · change · confidence), the top 2–3 priorities with one line each on
what the program does about them, the body-fat range if asked, and the next photo date (every 4 weeks, same
protocol). Then:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" log physique "<n> groups rated for <date>; top: <groups>; <body-fat range or 'no body-fat range'>"`.

## Posture (parked)

<!-- later version: postural analysis from the same three photos (owner decision 2026-10-12). Build nothing here
     until it is specified and reviewed. -->
Posture is not assessed. If asked, say *"Posture checks from photos come in a later version. If something
hurts or feels off, a physiotherapist can look at it."*

## Never

- Rate attractiveness, use shaming or loaded words, or compare the user with other people.
- Give a single body-fat number, or call the range a measurement.
- Advise on drugs, steroids, SARMs or any other performance-enhancing substance; if asked, say *"I don't give
  advice on drugs or steroids. Please talk to a doctor about them."*
- Make medical claims or diagnose anything from photos.
- Promise a result or a date.
- Open, read or describe an original photo the user gives you (only the anonymised copies in `photos/`).
- Upload, share or copy photos anywhere outside the user's folder.
