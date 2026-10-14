---
name: setup
description: Choose how CoAIch runs, your language and units, and where your training data comes from (Strong, Hevy, openGym, Apple Health or by hand), then check it works. Use when the user runs /setup, wants to add or change an integration or data source, or when onboard starts.
---

# Setup

Asks how the plugin runs and which integrations the user has, saves the answers in `coaich.md`, then checks
what can be checked on this computer. Runs first inside `/onboard`; the user can run `/setup` again any time.
Fields: `docs/athlete-folder.md` in this plugin.

Ask **one question at a time**, offer the answers as a short list, accept a number or the words. Plain words
only. In `language: es`, use the Spanish wording at the end.

## 0. The folder

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" find`. Not found → if `onboard` called this
skill, it has just made the folder: something is wrong, stop and say so. Otherwise say *"Run /onboard first: it
sets up your training folder."* and end.

Then run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" upgrade`. It prints one line. "upgraded …" →
tell the user, in their language, in one sentence: *"Your folder is now on the stable format: nothing in it
changed."* "already …" → say nothing. Exit 1 with "update the plugin" → say the folder was made by a newer CoAIch,
tell them to update the plugin (`/plugin`), and end.

On a re-run, show the current answers first (`setup.py check` prints them) and ask only about what the user wants
to change. A value the user keeps is not passed to `save`.

## 1. Questions

1. *"Where are you running CoAIch?"* Claude Code → `runtime: claude-code`. Say once: *"Versions for OpenAI Codex
   and Google Gemini CLI are planned."*
2. *"English or Spanish?"* → `language: en | es`.
3. *"Kilograms or pounds?"* → `units: kg | lb` (files always store kg).
4. *"Where do your workouts and health data come from? Pick all that apply."*
   - Strong (CSV export) → `strong-csv`
   - Hevy, connected account (needs Hevy Pro and the Hevy MCP server, see `skills/import/hevy.md`) → `hevy-mcp`
   - Hevy, CSV export → `hevy-csv`
   - openGym (its JSON export) → `opengym`
   - Apple Health, for steps, weight, sleep and body measurements, not workouts (a Health Auto Export JSON file,
     a paid app) → `apple-health`
   - None: I'll log by hand → `none`
5. Data arrives as files you export into this folder: `link: file`. Say once, without asking: *"A self-hosted
   server, so your data arrives without exporting, is on the roadmap."*

Save only the answers that changed:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup.py" save --runtime claude-code --language en --units kg --sources strong-csv,hevy-mcp --link file
```

Exit 2 names a bad value: ask that question again.

## 2. Experimental features

Do not ask here: `onboard` step 8 asks it, because it depends on age. Show the `experimental` value from
`setup.py check` and say: *"Nutrition and photo review are experimental and are {on|off}. To change it, ask me
(18 and over only), or run /onboard again."*

## 3. Check

For each chosen export source, ask where the file is (or say how to get it, as below; it can wait until the
first import). Then run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup.py" check [--strong F] [--hevy-csv F] [--opengym F] [--apple-health F]
```

Each line is `ok`, `fix` (the sentence after it says what to do) or `note`. Say every `fix` line in plain words.
It reads the files only: nothing is copied or imported.

| Source | How to get the file |
|---|---|
| Strong | Strong: Settings > Export Strong Data (CSV) |
| Hevy CSV | Hevy: Settings > Export & Import Data > Export Workouts |
| openGym | openGym: export your workouts as JSON |
| Apple Health | Health Auto Export app: export JSON, version 2, aggregated by day (see `skills/import/apple-health.md`) |

**Hevy MCP** can't be checked by the script. Make one read-only call: `get-workouts` (`page: 1`, `page_size: 1`). It answers → *"Hevy is connected."* Tool missing → *"The Hevy MCP server isn't set up: see `skills/import/hevy.md`."* An error → say it in plain words (a 401 means the API key is wrong). Never call a
Hevy tool that creates or updates.

## 4. Log

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" log setup "<runtime>, sources <list or none>, <n> fixes"`.

Called from `onboard` → go back to its next step. Otherwise, with a new source → offer the `import` skill.

## Spanish wording (`language: es`)

1. "¿Dónde usas CoAIch?" Claude Code. "Hay versiones previstas para OpenAI Codex y Google Gemini CLI."
2. "¿Inglés o español?"
3. "¿Kilos o libras?"
4. "¿De dónde vienen tus entrenos y tus datos de salud? Elige todos los que uses." Strong (exportación CSV) ·
   Hevy, cuenta conectada (necesita Hevy Pro y el servidor MCP de Hevy) · Hevy, exportación CSV · openGym
   (exportación JSON) · Apple Health, para pasos, peso, sueño y medidas corporales, no entrenos (archivo JSON de Health Auto Export) · Ninguno: lo apunto a mano
5. "Un servidor propio, para que tus datos lleguen sin exportar, está en la hoja de ruta."
- Experimental: "La nutrición y la revisión de fotos son experimentales y están {activadas|desactivadas}. Para
  cambiarlo, pídemelo (solo mayores de 18) o vuelve a ejecutar /onboard."
