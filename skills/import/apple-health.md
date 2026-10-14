# Apple Health via Health Auto Export

Apple Health has no export a script can read directly; the user exports with the
[Health Auto Export](https://apps.apple.com/app/id1115567069) iPhone app (paid features may apply).

## Export settings (tell the user once)

Format **JSON**, export version **2**, **Aggregate data on**, time grouping **Day**. Metrics: Step Count,
Resting Heart Rate, Heart Rate Variability, Active Energy, VO2 Max, Weight & Body Mass, Body Fat Percentage,
Waist Circumference, Sleep Analysis. Export a range of at least 7 days; overlaps with older exports are fine.

## Run

Save the file(s) to `data/raw/apple-health/` and run, **oldest first** (the last file wins a shared day):

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/import_apple_health.py" data/raw/apple-health/export-1.json data/raw/apple-health/export-2.json
```

It writes `data/health.csv` (`steps`, `sleep_h`, `hrv_ms`, `resting_hr_bpm`, `active_kcal`, `vo2max`,
`weight_kg`) and weight, waist and body fat to `data/body.csv`. A waist or weight typed by hand on the same
day stays. Impossible values (resting HR outside 30–120, HRV outside 5–250 ms, more than 60,000 steps, sleep
under 1 h or over 14 h, weight outside 30–250 kg) are dropped and listed. A weight jump over 3 kg in a day is
listed as "check": usually water or a scale error.

**Optional MCP path.** Health Auto Export can also run an MCP server on the phone. When the user has it
connected, ask for daily, aggregated metrics over a range of 7 days or more (a one-day query can leave out
steps and energy), save the result as JSON in `data/raw/apple-health/`, and run the same script. The app
must stay open on the phone during the pull.

## Trust tiers (how other skills may use these numbers)

| Signal | Tier | Use |
|---|---|---|
| Resting HR, steps, total sleep | Absolute | Daily values and 7-day trends |
| Body weight | Absolute, smoothed | 7-day average drives rate of change; never one weigh-in |
| HRV (SDNN, ms) | Trend only | 7-day mean vs the person's 30-day baseline; act only after 3+ days off baseline |
| VO2 max | Trend only | Monthly direction; watches underestimate fit people |
| Body fat %, lean mass (smart scale) | Trend only | Smoothed; hydration moves it day to day |
| Active energy | Not absolute | Week-to-week relative trend only; **never** sets or changes a calorie target |

Recovery calls need at least two signals agreeing (for example a low HRV trend plus a raised resting HR),
never one alone. None of this is a medical measurement.
