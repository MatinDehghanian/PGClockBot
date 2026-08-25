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
    def test_mobile_shell_uses_explicit_vvh_height(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("position: fixed;", shell)
        self.assertIn("height: var(--vvh, 100dvh);", shell)
        self.assertIn("min-height: var(--vvh, 100dvh);", shell)
        self.assertNotIn("inset: 0;", shell)
        self.assertNotIn("height: auto;", shell)
        self.assertIn("padding-bottom: 0;", shell)

    def test_mobile_body_uses_vvh_not_fixed_fill_available(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        block = mobile.split("html:has(.shell)", 1)[1].split(".shell {", 1)[0]
        self.assertIn("height: var(--vvh, 100dvh);", block)
        self.assertIn("overflow: hidden;", block)
        self.assertNotIn("position: fixed;", block)
        self.assertNotIn("-webkit-fill-available", block)

    def test_mobile_main_drops_desktop_height_chain(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        main = mobile.split("  .main {", 1)[1].split("  .main-body", 1)[0]
        self.assertIn("height: auto;", main)
        self.assertIn("max-height: none;", main)
        self.assertIn("flex: 1 1 0;", main)
        self.assertNotRegex(main, r"max-height:\s*var\(--vvh")

    def test_vvh_covers_layout_viewport_on_ios(self):
        html = BASE.read_text(encoding="utf-8")
        block = html.split("function setVVH()", 1)[1].split("setVVH();", 1)[0]
        self.assertIn("ios-safari", html)
        self.assertIn("visualViewport", block)
        self.assertIn("--vv-top", block)
        self.assertIn("window.__pgSetVVH = setVVH", html)

    def test_ios_safari_shell_tracks_visual_viewport(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn("html.ios-safari .shell", mobile)
        self.assertIn("top: var(--vv-top, 0px);", mobile)
        self.assertIn("background: transparent;", mobile.split("html.ios-safari .shell", 1)[1].split("}", 1)[0])
        self.assertIn("html.ios-safari .main", mobile)
        self.assertIn("html.ios-safari .side:not(.open)", mobile)
        self.assertIn("html.ios-safari .topbar", mobile)

    def test_ios_safari_theme_color_transparent(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertIn("ios-safari", html)
        self.assertIn("'transparent'", html)
        js = JS.read_text(encoding="utf-8")
        self.assertIn("ios-safari", js)
        self.assertIn("!root.classList.contains('ios-safari')", js)

    def test_no_scroll_nudge_on_load(self):
        js = JS.read_text(encoding="utf-8")
        self.assertNotIn("function nudge(el)", js)
        self.assertNotIn("nudgeAll", js)
        self.assertIn("ios-safari", js)
        self.assertNotIn("resample()", BASE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
