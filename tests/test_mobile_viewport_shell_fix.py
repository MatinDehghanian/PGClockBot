"""Mobile shell must pin to the viewport (no body strip / black bar)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
BASE = ROOT / "app/web/templates/base.html"
JS = ROOT / "app/web/static/panel.js"


class MobileViewportShellFixTests(unittest.TestCase):
    def test_mobile_shell_is_fixed_inset(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("position: fixed;", shell)
        self.assertIn("inset: 0;", shell)
        self.assertIn("height: auto;", shell)
        self.assertNotRegex(shell, r"(?m)^\s*height:\s*var\(--vvh")

    def test_mobile_body_scroll_locked_when_shell_present(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn("html:has(.shell)", mobile)
        self.assertIn("overflow: hidden;", mobile)
        self.assertIn("overscroll-behavior: none;", mobile)

    def test_vvh_prefers_inner_height_not_visual_viewport(self):
        html = BASE.read_text(encoding="utf-8")
        block = html.split("function setVVH()", 1)[1].split("setVVH();", 1)[0]
        self.assertIn("window.innerHeight", block)
        self.assertNotRegex(
            block,
            r"visualViewport\.height\s*\)\s*\|\|\s*window\.innerHeight",
            msg="visualViewport must not take precedence over innerHeight",
        )
        self.assertIn("window.__pgSetVVH = setVVH", html)

    def test_nudge_handles_short_pages(self):
        js = JS.read_text(encoding="utf-8")
        block = js.split("function nudge(el)", 1)[1].split("function nudgeAll", 1)[0]
        self.assertIn("minHeight", block)
        self.assertIn("__pgSetVVH", js)


if __name__ == "__main__":
    unittest.main()
