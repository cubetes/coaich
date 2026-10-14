<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/banner-dark.svg">
  <img src="docs/brand/banner-light.svg" alt="CoAIch. Stronger, for a reason. Example reason line: plus 2.5 kg, because 3 of 3 sets with 2 reps to spare.">
</picture>

[![checks](https://github.com/cubetes/coaich/actions/workflows/checks.yml/badge.svg)](https://github.com/cubetes/coaich/actions/workflows/checks.yml)
![licence: AGPL-3.0](https://img.shields.io/badge/licence-AGPL--3.0-0A0A0B?style=flat-square)
![plugin: 0.9 Achilles preview](https://img.shields.io/badge/plugin-0.9%20Achilles%20preview-A61E93?style=flat-square)
![apps: alpha](https://img.shields.io/badge/iPhone%20%26%20Watch-alpha-5E5A52?style=flat-square)

**A strength and nutrition coach for Claude Code. Every number comes with its reason. Your data stays in your folder.**

> **For now CoAIch is built for iPhone and Apple Health users.** Android (Health Connect) comes later.
>
> **Preview.** "CoAIch" is a working name until the trademark search is done. The plugin is version 0.9 (preview).
> See the [roadmap](docs/roadmap.md) and the [changelog](CHANGELOG.md).

## What it does

Most training apps tell you what to lift next and never say why. Most AI chats forget your last session.
CoAIch keeps your training in plain files in one folder. Every target comes with a reason you can check:

> You did 100 kg × 7, 7, 7, 7 with two reps to spare, so next week is 102.5 kg.

The main skills, in plain words:

- **Onboard and setup.** Asks a few questions, runs a medical check first, writes your profile and builds your first program.
- **Import.** Brings in your workouts from Strong, Hevy or openGym. From Apple Health (a Health Auto Export file) it
  brings in your steps, weight, sleep and body measurements such as body fat and waist.
- **Program build and audit.** Builds a program and checks it against the evidence.
- **Next targets.** Grades last week and proposes next week's load and reps, each with its reason. You say yes first.
- **Weekly review.** Imports, grades, proposes, asks, applies, and writes a check-in. With Hevy connected, it can
  send next week's targets to your Hevy routines, after you say yes.
- **Monthly check-in.** Four weeks of trends. Grades past changes. Plans the next month.
- **Roadmap and adapt.** Lays out the year. Rebuilds the plan around pain, fewer days or travel.
- **Feedback.** Drafts a GitHub post. You read it and post it yourself.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="plugin/docs/how-it-works-dark.svg">
  <img src="plugin/docs/how-it-works.svg" alt="How CoAIch works: you start once (setup, a safety check, a program you approve), then a weekly loop imports your workouts and Apple Health data, grades last week and proposes next week for your OK; every four weeks a monthly check-in plans the next month. Strong, openGym and Apple Health send files in; progress photos (front, side, back) have the face removed by Apple Vision on your Mac, then feed the monthly review; Hevy works both ways with your yes, and your Claude session runs on Anthropic. No CoAIch server.">
</picture>

**Experimental, off until you turn them on:** nutrition (calories, macros, meals) and physique (muscle ratings from
your progress photos).

## Install

From inside [Claude Code](https://claude.com/claude-code):

```
/plugin marketplace add cubetes/coaich
/plugin install coaich@coaich
```

From a clone of this repository, add the repository root instead: `/plugin marketplace add ./coaich`. You need
Python 3.9 or newer.

Then, in an empty folder for your training, run:

```
/onboard
```

`/onboard` starts with `/setup`. It asks where your workouts come from (Strong, Hevy, openGym or by hand) and
whether to read Apple Health for steps, weight and body measurements. Then it checks that it all works. Run
`/setup` again any time.

**Try it first.** Clone this repository and open `examples/demo-athlete`, a made-up athlete with 12 weeks of
training. The marketplace install does not include that folder. Run `claude` inside it, then `/weekly-review`. When
asked for the week, say 2030-W13.

```
| Session | Exercise | Target | Did | Grade | Next | Why | Your OK |
|---|---|---|---|---|---|---|---|
| lower-a-1 | Barbell Squat | 95×10·10·9·8 | 95×10·10·9·8 | met | 95×10·10·10·8 | Target met: same weight, one more rep on set 3 (9 → 10). | |
| lower-b-1 | Romanian Deadlift | 85×10·10·10·10 | 85×10·10·10·10 | met | 90×6·6·6·6 | 10 reps on every set with 3 reps left: +5 kg, reps back to 6. Needs your OK: load goes up on a spine-loaded lift. | ask |
```

The [plugin guide](plugin/README.md) has the full list of skills, the folder layout and the demo's other steps.

## Safety and privacy

- CoAIch does not replace a doctor. Some health answers stop the plan until a doctor has cleared you.
- Your data goes through your own Claude Code session, so Anthropic processes it under your account's terms.
- There is no CoAIch server and no telemetry. Other services are used only when you turn them on.
- **Your face never reaches Claude.** Photo review removes it on your own Mac first, with Apple Vision (the face and
  body detection built into macOS, offline). It cuts below the chin, or covers the head on back photos, strips the
  location and camera data, and keeps only that copy. If a face can't be removed with confidence, nothing is filed.
- Photos and food tools are opt-in and experimental. Read the [plugin guide](plugin/README.md) before you switch them on.
- The full [privacy policy](PRIVACY.md).

## Coming later

The order is: plugin first (now), then a web companion, then the iPhone and Apple Watch apps.

- **Web companion** (next): log sets and see your plans in any browser.
- **iPhone and Apple Watch apps** (last): in alpha today, not for other people yet. Details in the [roadmap](docs/roadmap.md).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/architecture-dark.svg">
  <img src="docs/architecture.svg" alt="The apps record your training and read Apple Health; your data reaches the Claude Code plugin on your computer through a link you choose (a file, a server on your own computer or your own Cloudflare account, or later CoAIch Pro); the plugin coaches and sends the plans back the same way">
</picture>

## Support CoAIch

CoAIch is free and open source, built by one person in the evenings. If it helps your training, you can support
its development:

- [GitHub Sponsors](https://github.com/sponsors/cubetes): monthly or one-off
- [Buy Me a Coffee](https://buymeacoffee.com/cubetes): a one-off thank-you
- [Ko-fi](https://ko-fi.com/cubetes): a one-off or monthly thank-you

Not a money thing? A star, a clear bug report or a shared link helps just as much.

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening an issue or a pull request. It also lists the repository
checks (`scripts/checks.sh`). Report security or privacy problems privately: see [SECURITY.md](SECURITY.md).

## How CoAIch is built

CoAIch is written with the help of Claude Code. A person decides what goes in, reviews every change and ships it.
The coaching rules are plain code with tests in [`plugin/scripts`](plugin/scripts), so a number never depends on
what a model says that day. The instructions Claude follows in this repo are in [CLAUDE.md](CLAUDE.md).

## Licence

[AGPL-3.0](LICENSE). Contributions need the CLA in [docs/CLA.md](docs/CLA.md).

## Trademarks

The code is AGPL-3.0. The CoAIch name and logo are not covered by the licence: forks are welcome under another name.
See [TRADEMARKS.md](TRADEMARKS.md).
