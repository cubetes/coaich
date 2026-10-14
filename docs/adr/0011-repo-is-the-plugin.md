# This repository is the plugin only

The owner's decision, 2026-10-14. `cubetes/coaich` holds the Claude Code plugin and nothing else. The plugin sits at
the repository root, not in `plugin/`.

- **The apps leave.** The iPhone, Watch and Live Activity code and the Swift engine (`Packages/AthleteCore`) were a
  public copy of the private app repository. That repository stays their only home. So do the app-only ADRs 0003
  (substitution keeps the slot), 0004 (the buddy never coaches) and 0005 (AI on the iPhone); their numbers are
  not reused.
- **Parity is checked on the app side.** The test that compared the app's program builder with
  `scripts/program_build.py` moves to the app repository with its fixture. Here, the shared target cases
  (`tests/fixtures/target_cases.json`) remain the contract any engine must pass (ADR 0006).
- **The root is the plugin.** `.claude-plugin/marketplace.json` uses `"source": "./"`; the plugin guide is
  `docs/guide.md`; the repository checks move to `tools/` so that `scripts/` holds only plugin code.

Consequences:
- An install copies the whole repository, `examples/demo-athlete`, `docs/`, `tests/` and `evals/` included.
- The Claude plugin directory refuses binary files and files over 256 KiB inside a plugin, and now the whole
  repository is inside. No binary file except `icon.png`, and no file over 256 KiB. The social preview image is
  uploaded in the GitHub settings instead of kept here.
- ADR 0006 stands: coaching rules are written here first, and the apps add none of their own.
