# Privacy policy

For the CoAIch plugin for Claude Code. Last updated 2026-10-14.

CoAIch is open-source software that runs on your own computer. Nobody behind CoAIch receives, stores or sees your
data: there is no CoAIch server, no account and no telemetry.

## What the plugin handles

Your training folder: workouts, body measurements (weight, waist, body fat), daily health metrics you import
(steps, sleep, heart rate), your answers to the onboarding and health questions, your plans and check-ins, and, if
you turn photo review on, progress photos with the face removed. The format is in
[docs/athlete-folder.md](docs/athlete-folder.md).

## Where it goes

- **Your folder, on your computer.** The plugin reads and writes only that folder. You can move, copy or delete
  it at any time; deleting it deletes everything CoAIch has.
- **Your own Claude session.** Claude reads the files it needs to coach you, so Anthropic processes them under
  the terms of your Claude account. CoAIch adds no other recipient.
- **Services you turn on, and only then:**
  - **Hevy** (through the Hevy MCP server you install): reads your workouts; sends routines only after you say yes.
  - **Apple Health**: a file you export yourself (Health Auto Export) and put in the folder. Nothing is fetched.
  - **openGym exercise names**: with `--fetch-names` and your OK, exercise catalogue numbers (no training data)
    are requested from openGym's public GitHub ([ADR 0009](docs/adr/0009-opengym-names-fetch.md)).
  - **Feedback**: `/feedback` opens a pre-filled GitHub page in your browser. Nothing is sent until you post it,
    and it never includes health data or names ([ADR 0008](docs/adr/0008-feedback-leaves-only-by-the-user.md)).
- **Photos**: the face is removed on your own computer before Claude sees a photo; location and camera data are
  stripped; the original is never opened by Claude. If a face can't be removed with confidence, nothing is filed.

`scripts/build_foods.py` calls the USDA FoodData Central API. It is a maintainer tool for rebuilding the
bundled food table; the plugin never runs it for you.

## Age and sensitive features

Under 16: no program. Calorie targets and photo review are off by default, adults only, and stay off for anyone
who reports an eating-disorder history or would rather not say. CoAIch does not replace a doctor.

## Contact

Privacy questions or problems: GitHub's private vulnerability reporting for this repository (see
[SECURITY.md](SECURITY.md)), or a public issue for anything that isn't sensitive.
