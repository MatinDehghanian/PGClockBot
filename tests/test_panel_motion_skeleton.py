"""Panel motion system — page loading veil removed in v8.5.22."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
JS = ROOT / "app/web/static/panel.js"
BASE = ROOT / "app/web/templates/base.html"


class MotionTokensTests(unittest.TestCase):
    def test_motion_css_vars(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("--motion-fast:", css)
        self.assertIn("--ease-out:", css)

    def test_buttons_and_nav_transition(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".btn:active:not(:disabled), a.btn:active", css)
        self.assertIn("transform: scale(0.96) translateY(0);", css)
        nav = css.split(".nav-item {", 1)[1].split("}", 1)[0]
        self.assertIn("transition:", nav)

    def test_modal_open_close_keyframes(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("@keyframes ui-modal-backdrop-in", css)
        self.assertIn("@keyframes ui-modal-out", css)
        self.assertIn(".ui-modal.open.is-closing", css)

    def test_reduced_motion_covers_chrome(self):
        css = CSS.read_text(encoding="utf-8")
        idx = css.index("@media (prefers-reduced-motion: reduce)")
        block = css[idx : idx + 900]
        self.assertIn(".ui-modal-panel", block)
        self.assertIn(".nav-item", block)


class NoPageLoadingTests(unittest.TestCase):
    def test_base_has_no_skeleton_or_veil(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertNotIn('id="page-skeleton"', html)
        self.assertNotIn('id="page-load-veil"', html)
        self.assertNotIn("__pgPageReveal", html)

    def test_js_has_no_skeleton_nav_intercept(self):
        js = JS.read_text(encoding="utf-8")
        self.assertNotIn("page-loading", js)
        self.assertNotIn("SKELETON_WAIT_MS", js)
        self.assertNotIn("armSkeleton", js)
        self.assertIn("function closeModal(el, opts)", js)


if __name__ == "__main__":
    unittest.main()
