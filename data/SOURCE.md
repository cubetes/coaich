# Bundled data — sources and licences

| File | Source | Licence |
|---|---|---|
| `exercises.json` | [free-exercise-db](https://github.com/yuhonas/free-exercise-db) `dist/exercises.json`, commit `a859101d633a01c4a1a920d6a8ce41dabba0705f`. Trimmed to `id, name, category, equipment, force, mechanic, level, primaryMuscles, secondaryMuscles` (no instructions, no images). 876 exercises. Same exercises and values as the CoAIch app's catalogue (kept in the app's repository), which keeps fewer fields. | The Unlicense (public domain) |
| `foods.csv` | [USDA FoodData Central](https://fdc.nal.usda.gov/) (U.S. Department of Agriculture, Agricultural Research Service), SR Legacy records, fetched 2026-10-12 by `scripts/build_foods.py`. 45 foods; each row keeps its `fdc_id`, data type and USDA description. Per 100 g: `kcal_100` = FDC nutrient 1008 (Energy), `protein_100` = 1003, `fat_100` = 1004, `carbs_100` = available carbohydrate (1005 by difference − 1079 fibre), `fibre_100` = 1079. Our own columns: `id`, `name`, `group`, `state`, `piece_g`, `contains` (diet and allergy tags written for CoAIch; oats tagged `gluten` for cross-contamination; tags are a guide, labels win). | Public domain (CC0 1.0, as FDC states). Our columns: AGPL-3.0 |
| `exercise_aliases.csv` | Written for CoAIch: common exercise names as Strong and Hevy show them → `exercises.json` ids. Every id is checked by `tests/test_exercise_map.py`. | AGPL-3.0, like the plugin |

To refresh `exercises.json`: download the file again, trim the same fields, update the commit above, run the tests
(the app's repository checks the build against the app over 11,086 cases).

To refresh `foods.csv`: `FDC_API_KEY=<your key> python3 scripts/build_foods.py` (the food list and our tags live
in that script), update the date above, run the tests (`tests/test_nutrition.py` checks every row).

**Not bundled, by rule.** Open Food Facts (ODbL, share-alike) may only be fetched on demand for one product the user
asks about, never copied into this repository. BEDCA and YAZIO data are not used.
