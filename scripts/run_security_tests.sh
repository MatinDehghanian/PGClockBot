#!/usr/bin/env bash
# Run the curated security regression test suite.
#
# This is the "no more security regressions" safety net requested after the
# 2026-08 security audit: every access-control / tenant-isolation /
# secret-handling fix gets a regression test, and every such test file is
# listed in scripts/security_test_manifest.txt so it always runs here — on
# every push/PR (see .github/workflows/security-tests.yml) and locally
# before shipping a patch.
#
# Usage:
#   scripts/run_security_tests.sh            # run the curated suite
#   scripts/run_security_tests.sh -k pattern  # forwarded to pytest
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

MANIFEST="scripts/security_test_manifest.txt"
if [ ! -f "$MANIFEST" ]; then
  echo "error: $MANIFEST not found" >&2
  exit 1
fi

mapfile -t FILES < <(grep -v '^\s*#' "$MANIFEST" | grep -v '^\s*$')

missing=0
for f in "${FILES[@]}"; do
  if [ ! -f "$f" ]; then
    echo "error: manifest lists missing file: $f" >&2
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  echo "Fix scripts/security_test_manifest.txt before running." >&2
  exit 1
fi

# Pre-existing, unrelated version-pin debt: several older audit test files
# also assert __version__ equals the version at the time they were written
# (e.g. "4.10.9"), which drifts on every release bump and has nothing to do
# with the security behavior those files actually guard. Deselect just those
# specific stale assertions so this suite stays a clean, trustworthy signal —
# any other failure here is a real regression, not release-version noise.
KNOWN_UNRELATED_FAILURES=(
  "tests/test_cancel_tickets_isolation_3_6_6.py::Version366Tests::test_version"
  "tests/test_final_audit_2_0_2.py::VersionBumpTests::test_version_is_current"
  "tests/test_full_audit_3_8_3.py::Version383Tests::test_version"
  "tests/test_security_audit_3_6_3.py::Version363Tests::test_version"
  "tests/test_v4_0_8_security_audit_sanitize.py::VersionTests::test_version"
)
DESELECT_ARGS=()
for nodeid in "${KNOWN_UNRELATED_FAILURES[@]}"; do
  DESELECT_ARGS+=("--deselect" "$nodeid")
done

echo "Running ${#FILES[@]} security regression test files..."
python3 -m pytest "${FILES[@]}" "${DESELECT_ARGS[@]}" -q "$@"
