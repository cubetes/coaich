# Bundled data — sources and licences

| File | Source | Licence |
|---|---|---|
| `exercises.json` | [free-exercise-db](https://github.com/yuhonas/free-exercise-db) `dist/exercises.json`, commit `a859101d633a01c4a1a920d6a8ce41dabba0705f`. Trimmed to `id, name, category, equipment, force, mechanic, level, primaryMuscles, secondaryMuscles` (no instructions, no images). 876 exercises. | The Unlicense (public domain) |
| `exercise_aliases.csv` | Written for CoAIch: common exercise names as Strong and Hevy show them → `exercises.json` ids. Every id is checked by `tests/test_exercise_map.py`. | AGPL-3.0, like the plugin |

To refresh `exercises.json`: download the file again, trim the same fields, update the commit above, run the tests.
