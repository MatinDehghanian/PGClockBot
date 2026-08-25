"""Mobile layout baseline v8.2.12 + Safari 26 / SW fixes outside shell/footer flex."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
BASE = ROOT / "app/web/templates/base.html"
JS = ROOT / "app/web/static/panel.js"
PWA = ROOT / "app/services/pwa.py"


class MobileViewportShellFixTests(unittest.TestCase):
    def test_mobile_shell_is_flex_dvh_not_fixed(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("display: flex;", shell)
        self.assertIn("height: 100dvh;", shell)
        self.assertNotIn("position: fixed;", shell)
        self.assertNotIn("--vvh", shell)

    def test_mobile_sticky_footer_like_v8212(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn(".main-body { flex: 1 0 auto;", mobile)
        footer = mobile.split("  .site-footer {", 1)[1].split("  .footer-meta", 1)[0]
        self.assertIn("margin-top: auto;", footer)

    def test_no_viewport_hack_scripts(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertNotIn("--vvh", html)
        self.assertNotIn("visualViewport", html)
        self.assertNotIn("__pgSetVVH", html)
        js = JS.read_text(encoding="utf-8")
        self.assertNotIn("__pgSetVVH", js)
        self.assertNotIn("visualViewport", js)

    def test_ios_safari_sampling_fix_without_layout_change(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn("html.ios-safari .shell", mobile)
        self.assertIn("background: transparent;", mobile.split("html.ios-safari .shell", 1)[1].split("}", 1)[0])
        self.assertIn("html.ios-safari .side:not(.open)", mobile)
        html = BASE.read_text(encoding="utf-8")
        self.assertIn("ios-safari", html)
        self.assertIn('id="meta-theme-color"', html)

    def test_service_worker_network_first_panel_assets(self):
        pwa = PWA.read_text(encoding="utf-8")
        self.assertIn("pgclock-shell-v5", pwa)
        self.assertIn("isVersionedPanelAsset", pwa)
        self.assertNotIn("'/static/panel.css'", pwa.split("PRECACHE")[1].split("];", 1)[0])


if __name__ == "__main__":
    unittest.main()
