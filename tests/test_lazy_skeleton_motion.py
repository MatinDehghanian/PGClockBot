"""Lazy skeleton removed — panel motion tokens remain."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
JS = ROOT / "app/web/static/panel.js"
BASE = ROOT / "app/web/templates/base.html"


class NoLazySkeletonTests(unittest.TestCase):
    def test_no_page_loading_in_js_or_base(self):
        js = JS.read_text(encoding="utf-8")
        html = BASE.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        self.assertNotIn("page-loading", js)
        self.assertNotIn("page-loading", html)
        self.assertNotIn("html.page-loading", css)
        self.assertNotIn(".page-load-veil", css)


class StrongerMotionTests(unittest.TestCase):
    def test_motion_tokens_longer(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("--motion-fast: 180ms;", css)
        self.assertIn("--motion-med: 280ms;", css)
        self.assertIn("--motion-slow: 380ms;", css)

    def test_modal_travel_is_visible(self):
        css = CSS.read_text(encoding="utf-8")
        block = css.split("@keyframes ui-modal-in {", 1)[1].split("}", 1)[0]
        self.assertIn("translateY(18px)", block)
        self.assertIn("scale(.96)", block)


if __name__ == "__main__":
    unittest.main()
