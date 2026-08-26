"""Mobile sidebar: open uses svh calc; closed collapses to height 0."""
from __future__ import annotations
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class MobileSideFullHeightTests(unittest.TestCase):
    def test_open_side_uses_svh_calc(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("100svh - var(--topbar-h)", side)
        self.assertNotIn("bottom: 0", side)

    def test_closed_side_height_zero(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        closed = mobile.split(".side:not(.open) {", 1)[1].split("}", 1)[0]
        self.assertIn("height: 0 !important;", closed)

if __name__ == "__main__":
    unittest.main()
