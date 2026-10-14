# The athlete-folder format is frozen as format 1

2026-10-14. 1.0 promises that a training folder keeps working. So the format in
[plugin/docs/athlete-folder.md](../../plugin/docs/athlete-folder.md) is frozen as **format 1**, recorded as
`coaich: 1` in `coaich.md`.

- **What is frozen:** every file, column, key, header field and block the contract describes. The labels inside
  some files stay as they are (`roadmap: 0.1`, `nutrition: 0.2`, `coaich.program/0.1`, `coaich/targets/0.1`):
  they are part of format 1, not separate versions to bump.
- **Allowed within format 1** (any MINOR release): a new optional file, a new `coaich.md` or `profile.md` key
  whose absence means the old behaviour, a new value where readers already fall back safely. Older plugins
  ignore all of these.
- **Needs format 2:** removing or renaming anything, changing what a value means, a new column in an existing
  CSV (an older plugin rewriting the file would drop it), a change to a CSV's key. Format 2 needs its own ADR, an
  upgrade step in `athlete_folder.py upgrade`, and a MAJOR version ([versioning](../versioning.md)).
- **A newer folder is refused.** `athlete_folder.find()` stops when `coaich:` is above what the plugin reads, and
  says to update the plugin, so an older plugin never rewrites files it doesn't understand.
- **0.x folders:** the public previews (0.3–0.8) already wrote format 1's files and columns. Their `coaich: 0.1`
  (or a missing key) reads as format 1 and `/setup` stamps it to `coaich: 1`. No data is changed.
