# Send routines to Hevy

Only when `data_sources` in `coaich.md` has `hevy-mcp`, the Hevy tools are available in this session, and the
athlete says yes this time. Numbers come from the script; Claude only carries them. Never delete anything in Hevy.

## 1. Build

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hevy_routines.py" build --dir .            # the week just applied
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hevy_routines.py" build --dir . --program  # a new program, no weights yet
```

Exit 2 lists exercises with no Hevy match. For each: `search-exercise-templates` with its name, show the athlete
the closest one or two, and save their choice:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hevy_routines.py" template --dir . <exercise_id> <template_id> "<Hevy title>"`.
Never pick on your own when two look alike. Then build again.

## 2. Send

For each routine in `data/hevy/routines_<week>.json` (the `title` and `exercises` exactly as written):
`search-routines` with its title.
- No routine with exactly that title → `create-routine`.
- Exactly one → `update-routine` with its id. This replaces that routine's exercises.
- More than one → stop and ask the athlete which to keep; send nothing for it.

Say once, the first time: *"CoAIch's routines end in '· CoAIch'. Rename one in Hevy and the next send makes a
new one, since Hevy can't delete routines through its API."*

## 3. Check

`get-routine` for each routine sent; save each answer unchanged to `data/raw/hevy-routines/<title>.json`, then:

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hevy_routines.py" verify --dir . --week <week> data/raw/hevy-routines/*.json
```

Only every line `ok` means it worked. Say any `different` or `missing` line in plain words and do not retry a
create (a retry can make a duplicate): check with `search-routines` first.
