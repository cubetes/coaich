# Hevy via the MCP server

Read-only weekly sync. Needs the Hevy MCP server installed by the user
([chrisdoc/hevy-mcp](https://github.com/chrisdoc/hevy-mcp), MIT, `npx -y hevy-mcp`, Node 24+) with their own
Hevy API key (Hevy Pro, Settings > Developer). The key stays in the user's MCP config, never in the athlete
folder. Use only the `get-*` tools here: sending routines to Hevy is a separate step with the athlete's yes
([../weekly-review/hevy-routines.md](../weekly-review/hevy-routines.md)).

If the Hevy tools are not available in this session, say so and offer the CSV export instead
(Hevy: Settings > Export & Import Data > Export Workouts → `import_hevy.py <file>`). Use the CSV too for a
first import of a long history: the MCP returns 10 workouts per page.

## Steps

1. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/import_hevy.py" --cursor` → the newest Hevy session date on file
   (`none` on a first sync).
2. Call `get-workouts` (`page: 1`, `page_size: 10`). It returns **summaries only** (id, title, start_time, no sets).
   Keep paging until a page holds a workout that started before the cursor date, or `page_count` is reached,
   and collect the ids of the workouts on or after the cursor date.
3. For each id, call `get-workout` (`workout_id`) and save the JSON result unchanged to
   `data/raw/hevy/<start date>-<id>.json`. Overlap is fine: re-sent workouts replace, not add.
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/import_hevy.py" data/raw/hevy/<those files>`
   (the script refuses a saved `get-workouts` page, since it has no sets).
4. Continue with step 3 of the skill (map new exercises).

## Notes

- Hevy gives times in UTC; the script turns them into this computer's local time. A workout first imported
  from the CSV and later through the MCP is recognised by start minute + title and replaced, not doubled
  (this needs the computer and the phone on the same time zone).
- Exercises are matched by their Hevy title. Hevy's own custom exercises land in the fix-up list.
- Hevy's API terms apply to the user's key; this plugin calls Hevy only through the user's MCP server.
