"""Scroll rubber-band / overscroll fixes (v8.2.8)."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
JS = ROOT / "app/web/static/panel.js"


class PageScrollContainerTests(unittest.TestCase):
    def test_main_and_side_allow_vertical_overscroll_bounce(self):
        css = CSS.read_text(encoding="utf-8")
        main = css.split(".main {\n", 1)[1].split("}", 1)[0]
        side = css.split(".side {\n", 1)[1].split(".main {", 1)[0]
        self.assertIn("overscroll-behavior-y: auto;", main)
        self.assertIn("overscroll-behavior-y: auto;", side)

    def test_mobile_main_scrolls_inside_shell_not_body(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        shell = mobile.split(".shell {\n", 1)[1].split("}", 1)[0]
        main = mobile.split("  .main {\n", 1)[1].split("}", 1)[0]
        self.assertIn("overflow: hidden;", shell)
        self.assertNotIn("overflow: visible;", shell)
        self.assertIn("overflow-y: auto;", main)
        self.assertIn("min-height: 0;", main)
        self.assertNotIn("overflow: visible;", main)

    def test_nav_open_locks_mobile_main_scroll(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn("body.nav-open .main { overflow: hidden !important; }", mobile)


class ModalOverscrollTests(unittest.TestCase):
    def test_modal_root_uses_contain_not_none(self):
        css = CSS.read_text(encoding="utf-8")
        block = css.split(".ui-modal {\n", 1)[1].split("}", 1)[0]
        self.assertIn("overscroll-behavior: contain;", block)
        self.assertNotIn("overscroll-behavior: none;", block)
        self.assertNotIn("touch-action: none;", block)

    def test_modal_guards_skip_interior_edge_prevent_default(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("function isModalInteriorScroller", js)
        self.assertIn("if (isModalInteriorScroller(modal, scroller)) return;", js)


if __name__ == "__main__":
    unittest.main()
