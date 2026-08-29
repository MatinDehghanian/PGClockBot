"""Mobile sidebar — bottom:0 stretch, no calc-dvh height."""
from __future__ import annotations

import unittest
from pathlib import Path

from css_blocks import at_rule, rule

ROOT = Path(__file__).resolve().parents[1]


class MobileSideFullHeightTests(unittest.TestCase):
    def test_side_uses_bottom_zero_not_calc_dvh(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8-sig")
        mobile = at_rule(css, "@media (max-width: 900px)")
        side = rule(mobile, ".side")
        self.assertIn("position: fixed;", side)
        self.assertIn("bottom: 0;", side)
        self.assertIn("height: auto;", side)
        self.assertIn("max-height: none;", side)
        self.assertNotIn("100dvh - var(--topbar-h)", side)
        self.assertNotIn("--safari-overlay", side)

    def test_side_safe_area_is_inner_not_box_shorten(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8-sig")
        mobile = at_rule(css, "@media (max-width: 900px)")
        side = rule(mobile, ".side")
        self.assertIn("padding: 0;", side)
        self.assertIn("bottom: 0;", side)
        self.assertNotIn("transform: translateX", side)
        self.assertNotIn("transform: translate3d", side)
        foot = mobile.split(".side .side-foot", 1)[1][:160]
        self.assertIn("padding-bottom: var(--bottom-inset);", foot)


if __name__ == "__main__":
    unittest.main()
