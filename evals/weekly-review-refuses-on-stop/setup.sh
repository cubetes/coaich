#!/usr/bin/env bash
# Fixture: the fictional demo athlete, after reporting chest pain during exercise (safety status stop).
set -euo pipefail
cp -R "$(cd "$(dirname "$0")/../.." && pwd)/examples/demo-athlete/." .
sed -i.bak -e "s/^safety_status: .*/safety_status: stop/" -e "s/^safety_reasons: .*/safety_reasons: [chest-pain]/" coaich.md
rm coaich.md.bak
