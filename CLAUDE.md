# CLAUDE.md

Instructions for Claude Code working in this repository. Humans: see CONTRIBUTING.md, which has the same rules.

## Layout

**This repository is the plugin** ([ADR 0011](docs/adr/0011-repo-is-the-plugin.md)); the apps live in their own
repository. **The plugin is the brain** ([ADR 0006](docs/adr/0006-plugin-is-the-brain.md)): apps record and show,
the plugin coaches. Coaching rules go here first; an app engine only copies what it needs offline, held to the
plugin by the shared target cases (`tests/fixtures/target_cases.json`). Never add a second sync protocol.

The repository root is the plugin, and everything in it is installed. Skills in `skills/*/SKILL.md`, scripts in
`scripts/` (Python standard library only), tests in `tests/` (`unittest`), the data contract in
`docs/athlete-folder.md`, the user guide in `docs/guide.md`. No binary file except `icon.png`, and no file over
256 KiB: the Claude plugin directory refuses them.

- `tools/`: the repository checks (not plugin code).
- `examples/demo-athlete`: the only athlete data allowed here. It is synthetic and generated; never hand-edit it.
- `docs/adr/`: decisions. `docs/versioning.md`: what bumps which version number.

## Before you finish

Run `tools/checks.sh`. It must end with `ALL CHECKS PASSED`. Never weaken a check, a test or the real-data guard
to make it pass: fix the cause, or stop and say what fails.

## Rules

- **Synthetic data only.** No real names, dates, weights, health records, device ids or photos anywhere, including
  tests, fixtures, commit messages and examples.
- **Photos:** never open an original photo. Only files the plugin has already anonymised. Changes to
  `scripts/photos.py` or `scripts/anonymise.swift` must keep this rule: when the face can't be removed with
  confidence, file nothing. Every refusal path has a test.
- **Safety gates** (the medical stop, the eating-disorder question, age limits) are in code with tests. Never move
  them into prompt text only, and never add a way to skip them.
- **Coaching numbers come from scripts**, never from mental arithmetic in a skill. A new rule cites its evidence
  (journal, year, DOI or PMID) in `references/`.
- Smallest change that fully solves the task. No new dependencies. A bug fix starts with a failing test.
- A change to the athlete-folder format or to what data leaves the computer needs an ADR first.
