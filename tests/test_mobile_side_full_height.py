"""Mobile sidebar stretches to the layout viewport bottom (not 100dvh cap)."""
from __future__ import annotations
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


class MobileSideFullHeightTests(unittest.TestCase):
    def test_side_uses_bottom_zero_not_dvh_calc(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("bottom: 0;", side)
        self.assertIn("height: auto;", side)
        self.assertIn("max-height: none;", side)
        self.assertNotIn("100dvh - var(--topbar-h)", side)
        self.assertIn("overscroll-behavior-y: contain;", side)

    def test_closed_ios_safari_drawer_leaves_viewport_bottom(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn("html.ios-safari .side:not(.open)", mobile)
        closed = mobile.split("html.ios-safari .side:not(.open)", 1)[1].split("}", 1)[0]
        self.assertIn("visibility: hidden;", closed)
        self.assertIn("bottom: auto;", closed)
        self.assertIn("height: 0;", closed)


if __name__ == "__main__":
    unittest.main()
