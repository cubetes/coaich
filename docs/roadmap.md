# Roadmap

Where CoAIch is and where it's going. Dates are targets, not promises: this is one person's project. What has shipped
is in the [changelog](../CHANGELOG.md). How versions are numbered: [versioning.md](versioning.md).

**For now CoAIch is built for iPhone and Apple Health users.** Your health data comes from Apple Health, and the
photo tools use Apple's face detection on a Mac. Android (Health Connect) and other platforms come later.

**The order (decided 2026-10-12): ship something useful as early as possible, then build on it.**

1. **1.0 "Achilles", the plugin**: the brain, usable on its own.
2. **2.0 "Bellerophon", the web companion**: see your plan and the coach's reasons in any browser, phone included,
   and tick your meals.
3. **3.0 "Cadmus", the iPhone companion**: the same, as a native iPhone app.
4. **4.0 "Diomedes", the iPhone and Apple Watch logger**: log your sets live in the gym.

(Decided 2026-10-13; see [versioning.md](versioning.md).)

## Where each part stands

| Part | Stage | Notes |
|---|---|---|
| **The plugin** (the brain) | Preview, 0.9 | 15 skills, 306 tests. Public. |
| **Web companion** | Private | Runs for the maintainer today (Spanish, one person). Needs English, a clean setup and the open server. |
| **Sync server** (the link) | Private | One person per server, on your computer or your own Cloudflare account. Not in this repo yet. |
| **iPhone app** | Alpha | Used daily by the maintainer. Not for other people yet. |
| **Apple Watch app** | Alpha | Same. Sits on top of the iPhone app, which works fully without it. |

## Step 1: the plugin, public (target December 2026)

- **Before publishing:** a trademark check of the name and logo.
- **First public version (0.3 "Achilles preview"): the training core.** Onboarding with the medical gate, imports (Strong, Hevy, Apple
  Health), program build and audit, next targets with their reasons, the weekly review and the roadmap.
- **Nutrition and photo review stay marked "experimental"** until a lawyer has reviewed their safety wording; they
  can be switched on, with every safeguard in code.
- **Import from openGym** (its JSON export, and its read-only MCP server), next to Strong and Hevy.
- **`/setup`**, run first by `/onboard` and again any time: where you run the plugin, which integrations you use
  (Strong, Hevy, openGym, Apple Health), how your data arrives, language and units, experimental features. It
  checks each integration works and says how to fix it if not.
- **`/feedback`**: send an idea or a problem to the project as a pre-filled GitHub Discussion or issue. Only safe
  details go with it (plugin version, operating system, which skills you used); never health data or names, and
  you see the exact text first. An optional, local usage count (off by default) can be attached when you choose.
- Done since launch: the evidence skill and scripted plugin evaluations (0.7), Spanish (0.8), a frozen
  athlete-folder format (0.9).
- Then **1.0 "Achilles"**: shared test cases with the app's engine, the Claude Code plugin marketplace.

## Step 2: 2.0, the web companion and the open server (target early 2027)

- **Publish the sync server:** one sync format, one open (AGPL) server, one person per server.
- **Setup guides** for running it on your own computer and on your own Cloudflare account.
- **The web companion:** see today's training and its targets with their reasons, your plan, the coach's weekly
  review and your weight trend; tick your meals and leave a day note, which the plugin reads back in the weekly
  review. Installable on the home screen, so it also covers Android. It shows and records; the plugin decides.
- No set logging in 2.0: that is 4.0.
- English and Spanish.

## Step 3: 3.0 the iPhone companion, then 4.0 the iPhone and Apple Watch logger (target mid 2027)

- **3.0:** the web companion's screens as a native iPhone app, Apple Health read by the app. Same data and plans,
  through the same link.
- **4.0:** logging in the gym on the iPhone and the Apple Watch (sets, rest timers, heart rate), starter programs,
  week-1 calibration, offline next targets. Public TestFlight, then the App Store.

## Alongside

### The brain on other AI tools
- The skills follow the open Agent Skills format (`SKILL.md`), which OpenAI Codex and Google Gemini CLI also read.
- Work needed: remove the Claude Code-only path variable from the skills, add an `AGENTS.md`, and test the full
  weekly loop on each tool before calling it supported.

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

- Posture analysis from progress photos.
- Importing gym body-scanner reports (for example 3D scanners) as their own trend.
- Tracking the music you train to.

Ideas and requests: GitHub Discussions. See [CONTRIBUTING.md](../CONTRIBUTING.md).
