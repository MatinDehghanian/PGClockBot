"""Mobile sidebar v8.2.12 height calc (not bottom:0 stretch)."""
from __future__ import annotations
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class MobileSideFullHeightTests(unittest.TestCase):
    def test_side_uses_dvh_calc_not_bottom_zero(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("100dvh - var(--topbar-h)", side)
        self.assertNotIn("bottom: 0", side)

if __name__ == "__main__":
    unittest.main()
