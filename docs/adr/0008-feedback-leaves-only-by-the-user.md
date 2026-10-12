# Feedback leaves the computer only when the user posts it

Owner decision, 2026-10-12. `/feedback` builds a pre-filled GitHub Discussion or issue; the user reads the exact text
and posts it themselves. The plugin never sends anything on its own, and there is no CoAIch server.

What can go with it:
- Always: the user's own words, the plugin version and the operating system name and version.
- Only when the user says yes at that moment, after seeing it: a count of how often each skill ran in the last
  90 days, taken from the folder's `log.md`. Skill names and counts only, never the log's results or dates.
- Never: health data, measurements, names or photos. The script warns when the text looks like it holds any
  (an email, a phone number, a date, body numbers with units), and the skill asks the user to remove them.

The post is public and carries the user's GitHub name; the content is what is anonymised. An anonymous channel
would need a server and is not built.
