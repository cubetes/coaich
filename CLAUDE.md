# CLAUDE.md

Instructions for Claude Code working in this repository. Humans: see CONTRIBUTING.md, which has the same rules.

## Layout

- `plugin/`: the Claude Code plugin. Skills in `plugin/skills/*/SKILL.md`, scripts in `plugin/scripts/` (Python
  standard library only), tests in `plugin/tests/` (`unittest`), the data contract in `plugin/docs/athlete-folder.md`.
- `Packages/AthleteCore`: the Swift engine for the app (Swift Testing). `iOS/`, `Watch/`, `LiveActivity/`: the app.
- `examples/demo-athlete`: the only athlete data allowed here. It is synthetic and generated; never hand-edit it.
- `docs/adr/`: decisions. `docs/versioning.md`: what bumps which version number.

## Before you finish

Run `scripts/checks.sh`. It must end with `ALL CHECKS PASSED`. Never weaken a check, a test or the real-data guard
to make it pass: fix the cause, or stop and say what fails.

## Rules

- **Synthetic data only.** No real names, dates, weights, health records, device ids or photos anywhere, including
  tests, fixtures, commit messages and examples.
- **Photos:** never open an original photo. Only files the plugin has already anonymised. Changes to
  `plugin/scripts/photos.py` or `anonymise.swift` must keep this rule: when the face can't be removed with
  confidence, file nothing. Every refusal path has a test.
- **Safety gates** (the medical stop, the eating-disorder question, age limits) are in code with tests. Never move
  them into prompt text only, and never add a way to skip them.
- **Coaching numbers come from scripts**, never from mental arithmetic in a skill. A new rule cites its evidence
  (journal, year, DOI or PMID) in `plugin/references/`.
- Smallest change that fully solves the task. No new dependencies. A bug fix starts with a failing test.
- A change to the athlete-folder format or to what data leaves the computer needs an ADR first.
