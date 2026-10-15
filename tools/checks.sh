#!/usr/bin/env bash
# Every pre-publish check. Runs locally and in CI (.github/workflows/checks.yml). Exit 1 on any finding.
# A missing scanner is skipped locally and fails when REQUIRE_SCANNERS=1 (CI).
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0

python3 tools/check_public.py --self-test && python3 tools/check_public.py . || fail=1
python3 tools/release_check.py --self-test || fail=1

# Plugin scripts: unit tests, including "examples/demo-athlete matches its generator".
python3 -m unittest discover -s tests || fail=1

if command -v gitleaks >/dev/null; then
  gitleaks dir . --config .gitleaks.toml --no-banner --redact || fail=1
  if git rev-parse --verify --quiet HEAD >/dev/null; then
    gitleaks git . --config .gitleaks.toml --no-banner --redact || fail=1
  fi
else
  echo "SKIP gitleaks: not installed"; [ "${REQUIRE_SCANNERS:-0}" = 1 ] && fail=1
fi

if command -v trufflehog >/dev/null; then
  trufflehog filesystem . --only-verified --fail --no-update || fail=1
  if git rev-parse --verify --quiet HEAD >/dev/null; then
    trufflehog git "file://$PWD" --only-verified --fail --no-update || fail=1
  fi
else
  echo "SKIP trufflehog: not installed"; [ "${REQUIRE_SCANNERS:-0}" = 1 ] && fail=1
fi

[ "$fail" = 0 ] && echo "ALL CHECKS PASSED" || echo "CHECKS FAILED"
exit "$fail"
