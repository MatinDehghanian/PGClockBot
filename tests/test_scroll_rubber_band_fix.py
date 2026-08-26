"""Scroll rubber-band / overscroll fixes."""

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

    def test_mobile_inner_main_scrolls_document_locked(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        shell = mobile.split(".shell {\n", 1)[1].split("}", 1)[0]
        main = mobile.split("  .main {\n", 1)[1].split("}", 1)[0]
        html_block = mobile.split("html:has(.shell)", 1)[1].split(".shell {", 1)[0]
        self.assertIn("overflow: hidden;", shell)
        self.assertIn("overflow-y: auto;", main)
        self.assertIn("overflow: hidden;", html_block)
        self.assertIn("100lvh", html_block)

    def test_nav_open_locks_mobile_main_scroll(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn("body.nav-open .main { overflow: hidden !important; }", mobile)


class ModalOverscrollTests(unittest.TestCase):
    def test_modal_root_uses_contain_not_none(self):
        css = CSS.read_text(encoding="utf-8")
        block = css.split(".ui-modal {\n", 1)[1].split("}", 1)[0]
        self.assertIn("overscroll-behavior: contain;", block)

    def test_modal_guards_skip_interior_edge_prevent_default(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("function isModalInteriorScroller", js)


if __name__ == "__main__":
    unittest.main()
