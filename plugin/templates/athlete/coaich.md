---
coaich: 0.1
language: en             # en | es
units: kg                # kg | lb (files always store kg)
runtime: claude-code     # where CoAIch runs (/setup); claude-code today
data_sources: []         # strong-csv | hevy-mcp | hevy-csv | opengym | apple-health; [] = logged by hand (/setup)
link: file               # how data arrives: file = exports you put in this folder (/setup)
safety_acknowledged:     # date the user accepted the medical warning (safety skill)
safety_acknowledgement:  # the exact sentence they accepted
safety_status:           # go | warn | stop (safety skill)
safety_reasons: []       # health item ids, age, red-flag:<area>
safety_clearance_date:   # date the user confirmed a doctor's clearance
safety_clearance_sentence: # exact sentence; one clearance lifts every stop item of that onboarding
experimental: off        # on | off: nutrition and photo review (safety texts not yet legally reviewed)
photo_anonymise: crop     # crop | blur: how the face is removed from progress photos (physique skill)
---
# CoAIch settings

This folder is your training folder. CoAIch reads and writes only the files in here.
Your data reaches Anthropic through your own Claude session (your account terms apply), and goes nowhere
else unless you turn on an integration (Hevy, Apple Health). Nothing goes to a CoAIch server: there isn't one.
