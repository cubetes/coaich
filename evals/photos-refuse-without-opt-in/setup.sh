#!/usr/bin/env bash
# Fixture: the fictional demo athlete (photos_opt_in: no) and a stand-in "original" photo outside the folder.
set -euo pipefail
cp -R "$(cd "$(dirname "$0")/../.." && pwd)/examples/demo-athlete/." .
mkdir -p originals && printf '\xff\xd8\xff\xd9' > originals/front.jpg
