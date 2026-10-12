# openGym exercise names may be fetched, with the user's OK

2026-10-12. An openGym backup stores built-in exercises by number only. To name them, `import_opengym.py` reads
openGym's own catalogue (AGPL-3.0 text; its pictures are licensed and never touched):

- `--catalogue DIR` reads a local openGym checkout. Nothing leaves the computer.
- `--fetch-names` downloads `catalogue/exercises/<id>.json` from openGym's public GitHub for the numbers used in
  the export, and only after the user agrees. What leaves the computer: those exercise numbers, in ordinary web
  requests to GitHub. No training data, weights, dates or names. Answers are treated as untrusted (JSON only, one
  short name each) and cached in the folder, so each number is fetched once.
- Without either, exercises arrive as "openGym <number>" for the user to name.

The catalogue is not copied into this repository.
