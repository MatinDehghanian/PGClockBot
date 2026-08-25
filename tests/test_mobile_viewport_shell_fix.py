"""Mobile shell uses the pre-v8.5.4 flex layout (no fixed shell / --vvh hacks)."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
BASE = ROOT / "app/web/templates/base.html"
JS = ROOT / "app/web/static/panel.js"


class MobileViewportShellFixTests(unittest.TestCase):
    def test_mobile_shell_is_flex_not_fixed(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("display: flex;", shell)
        self.assertIn("height: 100dvh;", shell)
        self.assertIn("max-height: 100dvh;", shell)
        self.assertNotIn("position: fixed;", shell)
        self.assertNotIn("--vvh", shell)

    def test_no_html_body_viewport_lock(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertNotIn("html:has(.shell)", mobile)
        self.assertNotIn("ios-safari", mobile)

    def test_mobile_main_body_sticky_footer_pattern(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        main_body = mobile.split("  .main-body {", 1)[1].split("  .site-footer", 1)[0]
        self.assertIn("flex: 1 0 auto;", main_body)

    def test_mobile_footer_sticky_like_v828(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        footer = mobile.split("  .site-footer {", 1)[1].split("  .footer-meta", 1)[0]
        self.assertIn("margin-top: auto;", footer)

    def test_base_has_no_vvh_script(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertNotIn("--vvh", html)
        self.assertNotIn("ios-safari", html)
        self.assertNotIn("visualViewport", html)
        self.assertIn('meta name="theme-color"', html)

    def test_panel_js_has_no_ios_viewport_sync(self):
        js = JS.read_text(encoding="utf-8")
        self.assertNotIn("ios-safari", js)
        self.assertNotIn("__pgSetVVH", js)
        self.assertNotIn("visualViewport", js)

    def test_global_shell_uses_dvh_not_vvh(self):
        css = CSS.read_text(encoding="utf-8")
        shell = css.split(".shell {", 1)[1].split(".side, .main", 1)[0]
        self.assertIn("height: 100dvh;", shell)
        self.assertNotIn("--vvh", shell)


if __name__ == "__main__":
    unittest.main()
