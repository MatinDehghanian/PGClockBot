"""Runs the Mini App browser-behavior checks (escaping, double taps, lost responses, back)."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MiniAppFrontendTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is required for browser-behavior checks")
    def test_miniapp_behavior(self) -> None:
        result = subprocess.run(
            [shutil.which("node"), str(ROOT / "tests/miniapp_app.test.cjs")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
