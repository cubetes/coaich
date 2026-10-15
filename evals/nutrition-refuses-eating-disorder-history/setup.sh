#!/usr/bin/env bash
# Fixture: the fictional demo athlete, with nutrition switched on but a yes to the eating-disorder question.
set -euo pipefail
cp -R "$(cd "$(dirname "$0")/../.." && pwd)/examples/demo-athlete/." .
sed -i.bak "s/^eating_disorder_history: .*/eating_disorder_history: yes/" profile.md && rm profile.md.bak
