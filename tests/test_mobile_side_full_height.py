"""Mobile sidebar stretches to the layout viewport bottom; closed drawer collapses."""
from __future__ import annotations
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


class MobileSideFullHeightTests(unittest.TestCase):
    def test_side_uses_bottom_zero_not_svh_calc(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("bottom: 0;", side)
        self.assertNotIn("--safari-overlay", side)
        self.assertIn("height: auto;", side)
        self.assertIn("max-height: none;", side)
        self.assertNotIn("100dvh - var(--topbar-h)", side)
        self.assertNotIn("100svh - var(--topbar-h)", side)
        self.assertIn("overscroll-behavior-y: contain;", side)
        self.assertIn("padding-bottom: calc(var(--foot-gap) + var(--safe-bottom));", side)
        self.assertIn("margin-top: calc(-1 * var(--space-1));", mobile)

    def test_closed_side_height_zero(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        closed = mobile.split(".side:not(.open) {", 1)[1].split("}", 1)[0]
        self.assertIn("height: 0 !important;", closed)
        self.assertIn("visibility: hidden;", closed)
        self.assertIn("bottom: auto;", closed)

    def test_no_overlay_inset_on_backdrop(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertNotIn("--safari-overlay", css)
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertNotIn("100lvh - 100svh", mobile)
        self.assertNotIn("100lvh - 100dvh", mobile)


if __name__ == "__main__":
    unittest.main()
