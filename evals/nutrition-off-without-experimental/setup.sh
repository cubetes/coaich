#!/usr/bin/env bash
# Fixture: a fresh copy of the fictional demo athlete in the run's working folder.
set -euo pipefail
cp -R "$(cd "$(dirname "$0")/../.." && pwd)/examples/demo-athlete/." .
sed -i.bak "s/^experimental: .*/experimental: off/" coaich.md && rm coaich.md.bak
