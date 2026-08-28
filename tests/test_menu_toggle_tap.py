"""Hamburger must open on pointerup, not wait for click-after-scroll-settle."""

from __future__ import annotations

import unittest
from pathlib import Path

from css_blocks import at_rule, rule


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app/web/static/panel.js"
CSS = ROOT / "app/web/static/panel.css"


class MenuToggleTapTests(unittest.TestCase):
    def test_pointerup_opens_before_click(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("pointerup", js)
        self.assertIn("toggleMenu", js)
        self.assertIn("ignoreClick", js)
        # pointerup path is registered (touch/pen); click remains for mouse.
        self.assertIn("e.pointerType === 'mouse'", js)

    def test_menu_toggle_uses_manipulation(self):
        mobile = at_rule(CSS.read_text(encoding="utf-8-sig"), "@media (max-width: 900px)")
        self.assertIn("touch-action: manipulation;", rule(mobile, ".menu-toggle"))

    def test_drawer_backdrop_is_not_a_scroll_lock(self):
        css = CSS.read_text(encoding="utf-8-sig")
        back = rule(css, ".side-backdrop")
        self.assertNotIn("touch-action: none;", back)
        self.assertNotIn("body.nav-open .topbar", css)


if __name__ == "__main__":
    unittest.main()
