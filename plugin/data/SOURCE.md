# data/exercises.json — source

free-exercise-db by yuhonas (https://github.com/yuhonas/free-exercise-db), `dist/exercises.json` at commit
`a859101d633a01c4a1a920d6a8ce41dabba0705f`, 876 exercises. Licence: The Unlicense (public domain). Trimmed to
the fields the scripts use:
`jq -c '[.[] | {id, name, equipment, primaryMuscles, secondaryMuscles, category, mechanic}]' exercises.json`.
Same file as the CoAIch app's catalogue (`Packages/AthleteCore/Sources/AthleteCore/Resources/exercises.json`).
