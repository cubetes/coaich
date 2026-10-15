# Contributing

Thanks for helping. CoAIch is run by one person with a few hours a week, so these rules keep it moving.
Issues are triaged about once a month.

## Where to go

| You have | Go to |
|---|---|
| A question, or an idea to talk through | GitHub Discussions |
| A bug you can reproduce | An issue (bug form) |
| A clear feature request with a use case | An issue (feature form) |
| Feedback from inside Claude Code | `/feedback` drafts the discussion or bug form for you to post |
| A security or privacy problem | [SECURITY.md](SECURITY.md), never a public issue |

**Never paste real health data, body measurements or photos** into an issue, a discussion or a pull request.
Reproduce with `examples/demo-athlete` instead.

## Before a pull request

- **Open an issue first** and wait for a yes, unless it's a typo. A pull request with no agreed issue may be closed.
- **At most 2 open pull requests per person.** Drafts don't count.
- **Every change needs a test.** Exempt: changes that only remove code (not to fix a bug), only touch comments,
  `.md` files or `.github/`. A bug fix starts with a test that fails without it.
- **No new dependencies.** The plugin scripts use the Python standard library only. Adding one is a hard sell.
- **Synthetic data only**, in code, tests and fixtures. `tools/checks.sh` must pass; it scans for real data,
  secrets and photo metadata.
- **A change to the athlete-folder format** (what an old folder can still read) needs an ADR in `docs/adr/` and a
  migration note in the changelog. See [docs/versioning.md](docs/versioning.md).
- **A change to what data leaves the computer** (photos, the folder, anything sent anywhere) needs an issue and an
  ADR before code.

```sh
tools/checks.sh                         # everything CI runs
python3 -m unittest discover -s tests   # just the plugin tests
```

## Plugin evals

`evals/` holds scripted conversations that check the skills keep their promises: asking before a heavier
spine-loaded lift, the safety stop (at onboarding and in the weekly review), nutrition off by default or after a
yes to the eating-disorder question, no photo opened or filed without the opt-in, nothing posted or sent to Hevy
without a yes. Each
case is a `prompt.md`, an optional `setup.sh` (copies `examples/demo-athlete` into the run's folder) and
`graders/*.md`. They call Claude, so they cost money and are not part of `tools/checks.sh`. A change to a
skill's consent or safety wording should keep them passing.

```sh
claude plugin eval . --runs 3 --scaffold --trust-plugin \
  --allow-tools Bash Write Edit --no-publish --max-cost-usd 30   # all cases, with a no-plugin baseline
claude plugin eval . --case 'feedback-*' ...                # one case, same flags
```

In GitHub, run the `plugin-evals` workflow by hand (Actions tab); it needs an `ANTHROPIC_API_KEY` secret.

## AI tools

Use any tool you like, including Claude Code. You are still the author:

- You read, understand and can explain every line you submit.
- You checked that the description is true. "Addressed the feedback" means you checked, not that a tool said so.
- No agent leftovers: no planning files, scratch notes or generated summaries in the change.

A pull request that breaks any of these, replaces the template, or whose description doesn't match the change may
be closed without review.

## How the code is written

- Write what's needed and no more. The shortest change that fully solves the issue.
- One source of truth: a rule lives in one place, and its tests sit next to it.
- No guessing in code: no heuristics where a rule or a question to the user will do.
- Error messages say what happened and what to do next. Log only what someone can act on.
- When `main` breaks, revert first and fix after.

## Supporting without code

Stars, clear bug reports and sharing the project help. You can also sponsor development: see the **Sponsor**
button at the top of the repository.

## Licence and CLA

Contributions are under the [AGPL-3.0](LICENSE). Pull requests also need the contributor licence agreement in
[docs/CLA.md](docs/CLA.md). Why: App Store terms conflict with the AGPL, so the official iPhone and Watch apps can only
include code whose authors gave the maintainer permission to release it under other terms. The CLA is that
permission. The code stays AGPL-3.0 for everyone else. The signing bot isn't switched on yet, so outside pull requests aren't merged yet.

## Labels

| Label | Means |
|---|---|
| `bug` | Something doesn't work as documented |
| `enhancement` | A new feature or a change in behaviour |
| `documentation` | Docs only |
| `privacy` | Touches health data, photos or what leaves the computer; reviewed first |
| `needs-info` | Waiting for the reporter; closed after 14 days with no reply |
| `duplicate` | Already reported; closed with a link |
| `wontfix` | Out of scope or not worth the cost; closed with the reason |
| `good first issue` | Small, clear and well described |

Issues are closed when they can't be acted on (you can't tell whether a change would fix them), bundle several
requests, or ask for a solution with no use case. Never just for being old. Vote with a 👍 on the issue, not a
"me too" comment.
