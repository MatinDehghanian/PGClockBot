"""Scroll model — mobile uses document scroll, desktop keeps inner main scroll."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
JS = ROOT / "app/web/static/panel.js"


class PageScrollContainerTests(unittest.TestCase):
    def test_desktop_main_allows_vertical_overscroll_bounce(self):
        css = CSS.read_text(encoding="utf-8")
        main = css.split(".main {\n", 1)[1].split("}", 1)[0]
        side = css.split(".side {\n", 1)[1].split(".main {", 1)[0]
        self.assertIn("overscroll-behavior-y: auto;", main)
        self.assertIn("overscroll-behavior-y: auto;", side)

    def test_mobile_document_is_scroll_owner_not_main(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        shell = mobile.split(".shell {\n", 1)[1].split("}", 1)[0]
        main = mobile.split("  .main {\n", 1)[1].split("}", 1)[0]
        doc = mobile.split("html:has(.shell)", 1)[1].split(".shell {", 1)[0]
        self.assertIn("overflow-y: auto;", doc)
        self.assertIn("overflow: visible;", shell)
        self.assertNotIn("overflow: hidden;", shell)
        self.assertIn("flex: 1 0 auto;", shell)
        shell_block = shell.split("}", 1)[0]
        for unit in ("100dvh", "100svh", "100lvh", "100vh"):
            self.assertNotIn(unit, shell_block)
        self.assertIn("overflow: visible;", main)
        self.assertNotIn("overflow-y: auto;", main)

    def test_nav_open_locks_document_scroll(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn("body.nav-open { overflow: hidden; }", mobile)
        self.assertNotIn("body.nav-open .main", mobile)


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
