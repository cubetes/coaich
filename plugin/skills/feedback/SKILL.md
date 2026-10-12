---
name: feedback
description: Send the project an idea, a problem or a question. Drafts a GitHub post the user reads and posts themselves; nothing is sent automatically.
disable-model-invocation: true
---

# Feedback

One script drafts the post: `${CLAUDE_PLUGIN_ROOT}/scripts/feedback.py`. It sends nothing. The user opens the
link and posts it themselves, under their own GitHub account.

## 1. Ask

1. *"Is this an idea, a problem, or a question?"*
2. *"Tell me in your own words."* Take their words as they are. Don't rewrite, summarise or add to them.

Say once: *"This will be public on GitHub. Please leave out health data, body measurements, names and photos."*

## 2. Draft

Write their words to a temporary file (`mktemp`), then:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/feedback.py" draft --kind idea|problem|question --text-file FILE
```

Add `--title "..."` only if the user gave one; otherwise the first line is the title.

- **WARNING lines**: the text has things that look like personal data (an email address, a phone number, a
  date, a body number with kg, lb, cm or %). Show each one and ask the user to remove or reword it. Rewrite the
  file only with their changes, and draft again. If they want to keep it, that is their choice.

Show the user the exact **TITLE** and **BODY**, as printed. It also carries the plugin version and the operating
system, nothing more.

## 3. Usage summary (optional)

Run the same command with `--usage` (from the athlete folder, or with `--dir`) and show the extra
`Skills run, last 90 days: …` line: skill names and how often each ran, nothing else. Ask:
*"Attach this usage summary? It helps us see how CoAIch is used."* Only a clear yes keeps it. Otherwise use the
draft without it.

## 4. Open

Give the **URL** as printed:

- idea → GitHub Discussions, Ideas; question → Discussions, Q&A. A GitHub account is needed to post.
- problem → a new issue with the bug form filled in. The user still fills in the steps and what they expected,
  and ticks the privacy box.

On macOS, offer to open it: *"Open it in your browser?"* After a yes, run `open "URL"`. Never post it for them.

## 5. Log

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/athlete_folder.py" log feedback "<idea|problem|question> drafted"
```

Only inside an athlete folder; skip it otherwise. Never put the user's text in the log.

## Never

- Post, send or submit anything for the user, or call GitHub yourself.
- Attach the usage summary without a yes given at this moment.
- Add anything from the athlete folder to the post besides that summary.
