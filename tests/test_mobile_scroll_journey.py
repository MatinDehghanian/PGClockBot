"""Full mobile scroll journey regression (first load → scroll → bottom → top)."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JOURNEY_PROBE = ROOT / "tests/mobile_scroll_journey_probe.py"


@unittest.skipUnless(JOURNEY_PROBE.exists(), "scroll journey probe missing")
class MobileScrollJourneyTests(unittest.TestCase):
    def test_short_and_long_scroll_journey_stable(self):
        proc = subprocess.run(
            [sys.executable, str(JOURNEY_PROBE)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        if proc.returncode != 0:
            self.fail(proc.stdout + "\n" + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["passed"], data.get("errors"))
        for name, steps in data["journeys"].items():
            first = steps["first_load"]
            after = steps["after_small_scroll"]
            back = steps["back_to_top"]
            self.assertFalse(first["scrollOwners"]["mainIsScroller"], name)
            self.assertEqual(first["scrollOwners"]["mainScrollTop"], 0, name)
            self.assertAlmostEqual(
                first["shell"]["rect"]["height"],
                after["shell"]["rect"]["height"],
                delta=2,
                msg=name,
            )
            self.assertAlmostEqual(
                first["gaps"]["footer_to_shellBottom"],
                after["gaps"]["footer_to_shellBottom"],
                delta=2,
                msg=name,
            )
            self.assertAlmostEqual(
                first["gaps"]["footer_to_shellBottom"],
                back["gaps"]["footer_to_shellBottom"],
                delta=2,
                msg=name,
            )


if __name__ == "__main__":
    unittest.main()
