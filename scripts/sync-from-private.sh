#!/usr/bin/env bash
# Copy an explicit allow-list from the private app repo into this public repo, then run every check.
# Reads the private repo's committed tree only (git archive), never its working files; writes nothing there.
#   scripts/sync-from-private.sh [PRIVATE_REPO] [REF]     defaults: ~/Dev/athlete-os-native HEAD
set -euo pipefail

SRC="${1:-$HOME/Dev/athlete-os-native}"
REF="${2:-HEAD}"
DST="$(cd "$(dirname "$0")/.." && pwd)"

# Only these paths ever leave the private repo. Add a path here only after reading every file in it.
ALLOW=(
  Packages/AthleteCore/Package.swift
  Packages/AthleteCore/Sources
  Packages/AthleteCore/Tests
  iOS
  Watch
  LiveActivity
  docs/adr
)

# Flagged inside the allow-list: kept out until fixed in the private repo (then delete the line).
EXCLUDE=(
  # Real owner data
  Packages/AthleteCore/Tests/AthleteCoreTests/Fixtures/demoSnapshot.json  # owner's real coach snapshot: weights, macros, dates, notes
  Watch/DemoPlan.swift                    # owner's real loads + dates + Hevy template ids
  Watch/Previews.swift                    # Hevy template id; builds on DemoPlan
  iOS/UITestFixture.swift                 # loads demoSnapshot.json; real 2026 dates
  Packages/AthleteCore/Sources/AthleteCore/Stats.swift   # owner's age hard-coded as the HR-zone fallback
  docs/adr/0001-tap-done-means-performed.md              # owner's logging stats (51 of 76 W1-W4 hits)
  docs/adr/0002-rir-not-rpe.md                           # owner's history size (28.6k Hevy sets)
  # Owner server / gyms (Release 2 features, gated off in Release 1)
  Packages/AthleteCore/Sources/AthleteCore/Sync.swift    # private Worker URL
  Packages/AthleteCore/Sources/AthleteCore/Gyms.swift    # owner's gym names
  # Tests with real dates, Hevy template ids, owner name or gyms (need synthetic data)
  Packages/AthleteCore/Tests/AthleteCoreTests/SessionTests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/RecheckFixTests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V032Tests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V035Tests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V040Tests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V050SyncTests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V050Tests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V060Tests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V070EntrenoTests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V071PhoneTests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V072PhoneTests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V080DirectTests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V080GymTests.swift
  # Clean, but they test the excluded Stats.swift / Sync.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V060WatchTests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V061Tests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V036Tests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V062Tests.swift
  Packages/AthleteCore/Tests/AthleteCoreTests/V072WatchTests.swift
  # Brand / metadata
  iOS/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png    # PNG text metadata (creation dates); brand not cleared
  Watch/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png  # same
)
# Not in ALLOW on purpose: project.yml (owner bundle id + Apple team id; references ExerciseImages and
# demoSnapshot.json), ExerciseImages/ (licence check pending), UITests/, WatchUITests/, scripts/ (device UDIDs),
# research/, docs/ other than adr/, AGENTS.md, CLAUDE.md, CONTEXT.md.

git -C "$SRC" rev-parse --verify --quiet "$REF^{commit}" >/dev/null || { echo "FAIL: $SRC has no commit $REF" >&2; exit 1; }

for p in "${ALLOW[@]}"; do rm -rf "${DST:?}/$p"; done   # deletions upstream disappear here too
specs=("${ALLOW[@]}")
for p in "${EXCLUDE[@]}"; do specs+=(":(exclude)$p"); done
git -C "$SRC" archive "$REF" -- "${specs[@]}" | tar -x -C "$DST"
echo "synced $(git -C "$SRC" rev-parse --short "$REF") from $SRC"

exec "$DST/scripts/checks.sh"
