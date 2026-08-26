"""Micro-fix regression: sidebar bottom + short-page footer flow."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests/mobile_micro_fix_probe.py"


@unittest.skipUnless(PROBE.exists(), "micro fix probe missing")
class MobileMicroFixTests(unittest.TestCase):
    def test_sidebar_and_short_page_geometry(self):
        proc = subprocess.run(
            [sys.executable, str(PROBE)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        if proc.returncode != 0:
            self.fail(proc.stdout + "\n" + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["passed"], data.get("errors"))


if __name__ == "__main__":
    unittest.main()
