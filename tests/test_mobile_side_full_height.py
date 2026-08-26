"""Mobile sidebar — bottom:0 stretch, no calc-dvh height."""
from __future__ import annotations
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MobileSideFullHeightTests(unittest.TestCase):
    def test_side_uses_bottom_zero_not_calc_dvh(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("position: fixed;", side)
        self.assertIn("bottom: 0;", side)
        self.assertIn("height: auto;", side)
        self.assertIn("max-height: none;", side)
        self.assertNotIn("100dvh - var(--topbar-h)", side)
        self.assertNotIn("--safari-overlay", side)

    def test_closed_side_no_height_collapse(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        side = mobile.split("  .side {", 1)[1].split("  .side.open", 1)[0]
        self.assertNotIn("height: 0", side)


if __name__ == "__main__":
    unittest.main()
