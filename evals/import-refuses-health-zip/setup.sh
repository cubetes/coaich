#!/usr/bin/env bash
# Fixture: a fresh copy of the fictional demo athlete in the run's working folder.
set -euo pipefail
cp -R "$(cd "$(dirname "$0")/../.." && pwd)/examples/demo-athlete/." .
mkdir -p data/raw/apple-health && python3 -c "import zipfile; zipfile.ZipFile(\"data/raw/apple-health/export.zip\", \"w\").writestr(\"apple_health_export/export.xml\", \"<HealthData/>\")"
