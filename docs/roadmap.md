# Roadmap

Where CoAIch is and where it's going. Dates are targets, not promises: this is one person's project. What has shipped
is in the [changelog](../CHANGELOG.md). How versions are numbered: [versioning.md](versioning.md).

**For now CoAIch is built for iPhone and Apple Health users.** Your health data comes from Apple Health, and the
photo tools use Apple's face detection on a Mac. Android (Health Connect) and other platforms come later.

**The order (decided 2026-10-12): ship something useful as early as possible, then build on it.**

1. **1.0 "Achilles", the plugin**: the brain, usable on its own.
2. **2.0 "Bellerophon", the measured coach**: the plugin again. Stalls, photo measures and posture trends worked out
   by scripts, and openGym both ways.
3. **3.0 "Cadmus", the web companion**: see your plan and the coach's reasons in any browser, phone included, and
   tick your meals.
4. **4.0 "Diomedes", the iPhone companion**: the same, as a native iPhone app.
5. **5.0 "Enkidu", the iPhone and Apple Watch logger**: log your sets live in the gym.

(Decided 2026-10-15, [ADR 0012](adr/0012-plugin-2-before-web.md); see [versioning.md](versioning.md).)

## Where each part stands

This repository is the plugin only. The other parts live in their own repositories.

| Part | Stage | Notes |
|---|---|---|
| **The plugin** (the brain) | Preview, 0.9 | 15 skills, 309 tests. Public. |
| **Web companion** | Private | Runs for the maintainer today (Spanish, one person). Needs English, a clean setup and the open server. |
| **Sync server** (the link) | Private | One person per server, on your computer or your own Cloudflare account. Its own repository when published. |
| **iPhone app** | Alpha | Used daily by the maintainer. Not for other people yet. Private repository. |
| **Apple Watch app** | Alpha | Same. Sits on top of the iPhone app, which works fully without it. |

## Step 1: the plugin, from 0.9 to 2.0

Done so far (0.3 to 0.9.1): the training core (onboarding with the medical gate, imports from Strong, Hevy, openGym
and Apple Health, program build and audit, next targets with their reasons, the weekly review, the roadmap),
`/setup`, `/feedback`, the evidence skill and scripted evaluations (0.7), Spanish (0.8), a frozen athlete-folder
format (0.9). Nutrition and photo review stay marked "experimental" until a lawyer has reviewed their safety
wording; they can be switched on, with every safeguard in code.

The next steps come from an October 2026 review of the plugin, other coaching apps and how expert coaches work.
Fixes come first. Anything that changes the targets the coach gives waits for 2.0, because a target change is a
major version ([versioning.md](versioning.md)).

| Version | Target | What it brings | Waits on |
|---|---|---|---|
| **0.9.2** | Oct 2026 | **Safety and correctness fixes.** The medical stop is enforced in code wherever targets are made or sent to Hevy, not only in the skill text. Two grading fixes: a week with no targets file is graded against the targets in force, not an unapplied proposal; RPE 7.5 becomes 3 reps left everywhere. Photo review refuses a picture with more than one person in it. The folder guide matches the photo code (chin margin, side and back photos). | Nothing |
| **0.10** | Nov 2026 | **Checks that catch regressions.** A test that every skill handoff and script path exists. Evaluations for every refusal (stopped athlete, the eating-disorder question, photos), run three times against a no-plugin baseline. A hook that blocks opening an original photo before it happens. | Nothing |
| **0.11** | Nov 2026 | **The six-photo protocol.** Front relaxed, front flexed, left and right side, back relaxed and back flexed, filed as `front-relaxed`, `front-flexed`, `side-left`, `side-right`, `back-relaxed`, `back-flexed`. The flexed front gets the grey-block cover the back pose uses, so raised arms stay in the picture; both sides follow the side-photo rule; every pose has its own refusal tests. Older three-photo sets stay readable. The physique skill, the rubric and the monthly check-in follow. | An ADR (the photo file names in the folder) |
| **1.0 "Achilles"** | Dec 2026 | **The first stable release.** Shared test cases with the app's engine, the Claude Code plugin marketplace, and `/coaich:start`, which looks at your folder and tells you the one next step and why. | The trademark check |
| **1.1** | Q1 2027 | **Pain that lingers is followed up.** A pain without red flags is asked about again; one that persists or gets worse leads, in code, to a physiotherapist referral or a stop. | An ADR (optional keys on pain entries) |
| **1.2** | Q1 2027 | **Import from any app or spreadsheet.** Map a CSV's columns once; you declare the date format and units, check the first and last rows, and say yes before anything is written. | An ADR (the saved mapping file) |
| **1.3** | Q2 2027 | **openGym without exporting by hand**: read through openGym's own MCP server, with your exercise matches saved. | Checking the tool shapes against openGym's source |
| **1.4** | Q2 2027 | **Stalls worked out by a script.** A robust trend (Theil–Sen) over each lift's estimated one-rep max labels it rising, flat or falling. The coach reads the label instead of judging; the targets stay the same. | Evidence rows in `references/` |
| **1.5** | Q2 2027 | **The brain on other AI tools.** An `AGENTS.md`, no Claude Code-only path variable in the skills, and the full weekly loop tested on OpenAI Codex and Google Gemini CLI before calling them supported. | The weekly loop passing on each tool |
| **2.0 "Bellerophon"** | mid 2027 | **The measured coach.** Stalls drive exercise swaps and easy weeks. Bigger jumps from "reps left" are capped for beginners and long sets if the evidence review supports it. Photo review adds measured numbers (proportions, symmetry, change over time) next to Claude's ratings, and says when the two disagree. Optional posture notes: alignment trends from your anonymised photos, with no diagnosis and no pain claims. openGym both ways: next week's targets sent as routines, with your yes. A new set of shared target cases, which the apps' engines must follow. | The lawyer's review of the photo wording; ADRs for photo measures and openGym writing; the photo benchmark (`tools/photo_bench.py`): the chosen model's ratings reach kappa 0.6 or more against an expert; an openGym round trip on a test instance; the evidence review on reps-left accuracy |

## Step 2: 3.0, the web companion and the open server (target late 2027)

- **Publish the sync server:** one sync format, one open (AGPL) server, one person per server.
- **Setup guides** for running it on your own computer and on your own Cloudflare account.
- **The web companion:** see today's training and its targets with their reasons, your plan, the coach's weekly
  review and your weight trend; tick your meals and leave a day note, which the plugin reads back in the weekly
  review. Installable on the home screen, so it also covers Android. It shows and records; the plugin decides.
- No set logging in 3.0: that is 5.0.
- English and Spanish.

## Step 3: 4.0 the iPhone companion, then 5.0 the iPhone and Apple Watch logger (target 2028)

- **4.0:** the web companion's screens as a native iPhone app, Apple Health read by the app. Same data and plans,
  through the same link.
- **5.0:** logging in the gym on the iPhone and the Apple Watch (sets, rest timers, heart rate), starter programs,
  week-1 calibration, offline next targets. Public TestFlight, then the App Store.

## Alongside

### CoAIch Pro (after step 3)
- The same open server, run by us on EU servers: nothing to set up. A hosted weekly coaching report. Price decided
  after a beta.

### Other ways to install the iPhone app, in the EU (to explore, with step 3)
EU rules (since iOS 17.4) allow iPhone apps outside Apple's App Store. The App Store stays the main channel, and the
CLA stays: these are extra channels, for EU users only.
- **Other app stores**, such as AltStore PAL (itself AGPL-licensed): an AGPL build of the app, listed there.
- **Installing straight from our website** (Apple's web distribution).

What we found (2026-10-12; Apple's EU terms changed on 1 October 2026):

| Question | Finding | Confidence |
|---|---|---|
| Does the **Apple Watch** app install this way? | Apple's pages describe these channels for iPhone and iPad apps only. Nothing says a Watch app comes along. | Probably not. Test on a device before relying on it. |
| Do these channels **clash with the AGPL**? | The App Store problem is Apple's licence for users. In these channels the developer sets the terms, and AltStore PAL itself is AGPL software distributed this way. Apple still signs and checks every app. | Our guess: much lower risk than the App Store. Not legal advice. |
| **Fees** | No per-install fee any more. A 5 % commission applies only to sales (paid apps, in-app purchases). A free app pays nothing. The developer program is still $99 a year. | Confirmed by Apple's announcement. |
| Who can **list in another store** (e.g. AltStore PAL) | Any developer: the app is notarized by Apple and hosted by us. | Likely. |
| Who can **install from their own website** | No EU company needed any more. You must pass a financial bar: a Dun & Bradstreet score, public listing, venture funding, or an accountant's audit. | Confirmed. A new one-person company probably doesn't qualify at first. |

So: an AGPL iPhone build on AltStore PAL is the realistic first step. That is a complete app on its own: the iPhone
app does everything the Watch app does (logging, rest timers, the live workout), and the Watch is an extra on top of
it. If the Watch app can't come along, EU users of that build train from the phone; the Watch keeps needing the
App Store or TestFlight. Web distribution waits until the company can pass the financial bar.

## Parked (not scheduled)

- Importing gym body-scanner reports (for example 3D scanners) as their own trend.
- Tracking the music you train to.

Ideas and requests: GitHub Discussions. See [CONTRIBUTING.md](../CONTRIBUTING.md).
