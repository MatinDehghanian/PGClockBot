"""Lazy skeleton (slow loads only) + stronger panel motion."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
JS = ROOT / "app/web/static/panel.js"
BASE = ROOT / "app/web/templates/base.html"


class LazySkeletonTests(unittest.TestCase):
    def test_no_forced_min_delay_in_js(self):
        js = JS.read_text(encoding="utf-8")
        self.assertNotIn("minMs", js)
        self.assertNotIn("pg-page-nav", js)
        self.assertIn("__pgPageReveal", js)

    def test_skeleton_armed_after_wait_only(self):
        html = BASE.read_text(encoding="utf-8")
        boot = html.split("Skeleton only if", 1)[1].split("</script>", 1)[0]
        self.assertIn("setTimeout", boot)
        self.assertIn("page-loading", boot)
        self.assertIn("__pgPageReveal", boot)
        self.assertIn("280", boot)
        self.assertNotIn('classList.add("page-booting")', boot)
        self.assertNotIn("pg-page-nav", html)

    def test_content_visible_by_default(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertNotIn("html.page-booting .page-surface", css)
        self.assertIn("html.page-loading .page-skeleton", css)
        self.assertIn("page-was-slow", css)


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

    def test_button_hover_lift(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("transform: translateY(-1px);", css)
        self.assertIn("transform: scale(0.96) translateY(0);", css)


if __name__ == "__main__":
    unittest.main()
