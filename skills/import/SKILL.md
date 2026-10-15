---
name: import
description: Bring training and health data into the athlete folder from a Strong CSV export, Hevy (MCP or CSV export), an openGym backup or Apple Health (Health Auto Export JSON). Use when the user shares an export, says "import my Strong export", "sync Hevy", "pull my workouts", "sync Apple Health" or "update my weight and steps", or before a review that needs fresh data.
---

# Import

Turns a third-party export into the athlete folder's own files (`docs/athlete-folder.md` in this plugin):
`data/sets.csv`, `data/sessions.csv`, `data/body.csv`, `data/health.csv`, and the fix-up list
`data/exercise_map.csv`. Every importer is **safe to run again**: a re-sent session or day replaces the old
one and is never counted twice. Exports are kept untouched in `data/raw/<source>/`.

Scripts live in `${CLAUDE_PLUGIN_ROOT}/scripts/`; run them from the athlete folder (or pass `--dir`).
If they say there is no `coaich.md`, run `/onboard` first.

## 1. Pick the source

Use `data_sources` in `coaich.md`, or what the user names. Ask only if both are silent.

| Source | What the user gives | Run |
|---|---|---|
| Strong | the CSV from Strong: Settings > Export Strong Data | `import_strong.py <file>` |
| Hevy, first import or long history | the CSV from Hevy: Settings > Export & Import Data > Export Workouts | `import_hevy.py <file>` |
| Hevy, weekly sync | nothing: the Hevy MCP server (needs Hevy Pro + an API key) | [hevy.md](hevy.md) |
| openGym | the backup from openGym: Settings > Data & backup > Export backup (JSON), `opengym-backup-<date>.json` | `import_opengym.py <file>` plus a name source (below) |
| Apple Health | a JSON export from the Health Auto Export app | [apple-health.md](apple-health.md) |

Save a file the user drops in the chat to `data/raw/<source>/` first, with its original name.

## 2. Run the importer

Only a file that matched a row in step 1 gets here. Anything else (the Health app's own `export.zip`, a PDF, a
screenshot) is refused as its source page says, and never run through an importer.

To save tokens, hand the run to the `clerk` agent (Agent tool, `coaich:clerk`, on Haiku) with the exact command,
and show its reply: the importer's summary as printed. Confirm it with one line of the log (`tail -n 1 log.md`).
The fix-up questions in step 3 stay with you: only you talk to the athlete.

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/import_strong.py" data/raw/strong/strong.csv
```

- **Strong, older export without a unit** (header has `Weight`, not `Weight (kg)`): the script uses `units` from
  `coaich.md`; if that is missing it stops and asks for `--unit kg` or `--unit lb`. Ask the user which unit
  Strong was set to. Never guess: a wrong unit makes every load 2.2× off.
- **openGym:** the JSON backup holds workouts and weigh-ins (weigh-ins go to `body.csv`, source `opengym`). It
  names openGym's built-in exercises only by number. If the user has an openGym folder (self-hosted, or a clone),
  pass `--catalogue <that folder>`. Otherwise ask first: "This downloads only openGym's public exercise names,
  sending just the exercise numbers. OK?" On yes, add `--fetch-names` (once; names are cached in
  `data/opengym_names.json`). On no, import without either: those exercises arrive as `openGym <id>`. The
  .zip "with photos & videos" is refused: ask for the plain JSON. A self-hosted server's `data/state-<user>.json`
  has the same shape and imports the same way. Reading openGym live through its read-only MCP server is a later
  option, not built.
- A script that exits with an error has written nothing. Show its message in plain words.

## 3. Map new exercises

The importers match every exercise name to a free-exercise-db id (bundled at `data/exercises.json` in the
plugin, with common Strong/Hevy names in `data/exercise_aliases.csv`). A name they cannot match is stored as
`custom:<slug>` and listed under "Exercises to map".

For each listed name, search the catalogue (`grep -i "<word>" "${CLAUDE_PLUGIN_ROOT}/data/exercises.json"`),
propose the closest id, and on the user's OK write it into `data/exercise_map.csv` (`exercise,exercise_id`).
Then run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/exercise_map.py"`: every set, old and new, takes the fix.
An openGym exercise imported without a name arrives as `openGym <id>`: re-run with `--catalogue` or (after the
user's OK) `--fetch-names`, or map it by hand like any other. Leave a name on `custom:` when nothing in the catalogue is the same movement; a custom id the user picks
(`custom:zercher-carry`) is kept too. An id that is not in the catalogue is reported back: fix the typo.

## 4. Report

Show the script's summary in a few lines: sessions and sets (new vs updated), dropped rows and why, days of
health data, and the exercises still to map. Example:

> Imported 12 Strong sessions (3 new), 214 sets. 1 row dropped (9,999 kg, a typing error).
> 2 exercises still to map: Belt Squat (Machine), Sandbag Carry.

The importers append the `log.md` line themselves; add nothing more. Its exact form,
`- YYYY-MM-DD · import · <source>: <n> sessions, <m> sets through YYYY-MM-DD` (Apple Health:
`apple-health: <n> days through YYYY-MM-DD`), is read by the progression skill's stale-data check.

## Rules

- Read-only towards every app. This skill never writes to Hevy or Apple Health.
- Weights are stored in kg; the display unit is `units` in `coaich.md`.
- RPE becomes RIR (reps left) as `10 − RPE`, rounded, 0–5. Warm-up sets never count as working sets.
- Health data follows the trust tiers in [apple-health.md](apple-health.md): never set calories from watch
  energy, never act on one day of HRV.
