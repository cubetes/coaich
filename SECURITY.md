# Security and privacy

CoAIch handles health data and body photos. A privacy leak is a security bug here.

## Reporting

Use GitHub's **private vulnerability reporting**: the "Report a vulnerability" button under the Security tab.
Don't open a public issue, and don't attach real photos or real health data: describe the case, or reproduce it with
`examples/demo-athlete`.

This is a hobby project run by one person. There is no promised response time: expect days, not hours. Fixes go
into the latest release only.

## In scope

- A face, or part of one, left in a photo the plugin filed (`scripts/photos.py`, `scripts/anonymise.swift`).
- Metadata (GPS, dates, device) left in a filed photo or anywhere in the repository.
- A way to make the plugin send athlete-folder data anywhere other than the user's own Claude session.
- Real personal data in the repository, or a way around `tools/checks.sh`.
- A safety gate that can be skipped: the medical stop, the eating-disorder question, the under-18 limits.
- Secrets in the repository or its history.

## Out of scope

- Coaching advice you disagree with: open an ordinary issue.
- Problems in Claude Code, Claude, macOS or Apple Vision themselves: report those to Anthropic or Apple.
- Anything that needs someone who already controls your computer.

## What CoAIch protects, and what it doesn't

| Does | Doesn't |
|---|---|
| Removes the face on your computer before Claude sees a photo, and keeps only that copy | Encrypt the athlete folder: it's plain files, protected only by your computer's login |
| Strips all metadata from every filed photo | Keep what Claude reads private from Anthropic: it goes to Anthropic under your own Claude account and its terms |
| Keeps your data in your folder: there is no CoAIch server, account or analytics | Back up your folder |
| Refuses (files nothing) when a face can't be removed with confidence | Guarantee the detector never misses: check each filed photo, as the `physique` skill does |
