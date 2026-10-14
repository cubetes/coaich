# The plugin is the brain; the apps are wrappers; the link between them is the user's choice

> Where the code lives is superseded by [ADR 0011](0011-repo-is-the-plugin.md): this repository is the plugin
> only, and the apps and their Swift engine live in their own repository. The rest of this decision stands.

The owner's split (2026-10-12).

**The apps** (iPhone, Apple Watch, web) are where you train: they record sets and sessions and adherence, show your
plans (training, diet, schedule) and your lift statistics. The iPhone app reads Apple Health, since it holds that
permission. Their data lives on the phone, or syncs to a server.

**The plugin is the brain.** It runs on your own computer, in Claude Code today (OpenAI Codex and Google Gemini
CLI read the same skill format and are planned, see the roadmap), reads that data, does all the coaching
(onboarding and the safety gates, programs, next targets, weekly reviews, monthly check-ins, nutrition, photo
review, roadmaps) and sends the plans back. The apps add no coaching rules of their own.

**The link between them is the user's choice**, and it carries the same two things every time: data up to the
plugin, plans back to the apps.

| Link | Who runs it |
|---|---|
| A file (CSV/JSON export dropped into the athlete folder) | Nobody: no server. Release 1, local only. |
| A local server | You, on your own computer |
| Cloudflare | You, on your own Cloudflare account |
| CoAIch Pro (later) | Us, on our servers |

Consequences:
- **One person per server, for now.** A local or Cloudflare server serves its owner only; there is no multi-user
  sign-in. Pro is the exception, run by us.
- **One sync format, one server.** Local, Cloudflare and Pro run the same open server (AGPL); Cloudflare is
  the reference deployment and Pro is that server run by us. A file is the same data written to disk. There is
  never a second protocol to maintain.
- The plugin's data contract (`plugin/docs/athlete-folder.md`) is what every link delivers: what the apps log is
  what the plugin reads, and the plans the plugin writes are what the apps show.
- Apple Health reaches the plugin through the iPhone app. The plugin's own Apple Health import, and the Strong and
  Hevy imports, stay for people without the apps.
- A coaching rule is written, cited and tested in `plugin/` first. The app keeps an offline Swift copy of the rules
  it needs in the gym (`Packages/AthleteCore`), because a next target must appear with no connection; shared test
  cases hold it to the plugin's answers, and when they disagree, the plugin is right.

Open: the sync format itself (endpoints, auth, conflict rule) is specified when the server is published.
