# CoAIch (working name)

A strength-training app for iPhone and Apple Watch. Log your sets on the Watch or the phone and,
after every session, see the next target for each exercise **with the reason for it**.

> Pre-release. The name is a placeholder until a trademark search is done.

## Release 1

- **Free.** No payments, no subscription.
- **Local.** Your data stays on your devices. No account, no server, no analytics. CSV export.
- **Starter programs.** Pick one (full-body 3 days, upper/lower 4 days, push/pull/legs 6 days).
- **Week 1 measures you.** Your first working set and its reps in reserve set your next target.
- **Auditable.** The next-target rule lives in plain Swift in `Packages/AthleteCore`, with tests.
  Read it to see exactly why the app suggests a load.

## Build

Requirements: Xcode with the iOS 27 / watchOS 27 SDKs, Swift 6.

```sh
cd Packages/AthleteCore && swift test     # the engine and its tests
```

The Xcode project for the app targets is not published yet. It will be generated with
[XcodeGen](https://github.com/yonaskolb/XcodeGen) from a `project.yml` that comes in a later sync.

## Claude Code plugin

`plugin/` is CoAIch as a Claude Code plugin: the same coaching rules, working on plain files in your own
training folder. See [plugin/README.md](plugin/README.md).

```
/plugin marketplace add <org>/coaich
/plugin install coaich@coaich
```

## Repository checks

`scripts/checks.sh` runs before anything is published, locally and in CI:

| Check | What it stops |
|---|---|
| gitleaks, trufflehog (`--only-verified`) | Secrets and keys |
| `* 2.*` names | iCloud duplicate files |
| Image metadata | EXIF, XMP and PNG text chunks (dates, locations, devices) |
| Real-data guard (`scripts/real-data-guard.txt`) | Personal names, device ids, private hosts, gym names, real dates in test data |

This repository is filled by an allow-list copy from a private repository
(`scripts/sync-from-private.sh`). Only listed paths are copied; flagged files stay out.

## Licence

[AGPL-3.0](LICENSE). Contributions need the CLA in [docs/CLA.md](docs/CLA.md) (draft).

## Trademarks

The code is AGPL-3.0. The CoAIch name and logo are not covered by the licence: forks are welcome under another name. See `TRADEMARKS.md`.
