"""Mobile shell fills 100lvh (layout viewport), not 100dvh (small viewport)."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
BASE = ROOT / "app/web/templates/base.html"
JS = ROOT / "app/web/static/panel.js"
PWA = ROOT / "app/services/pwa.py"


class MobileViewportShellFixTests(unittest.TestCase):
    def _mobile(self) -> str:
        return CSS.read_text(encoding="utf-8").split("@media (max-width: 900px)", 1)[1]

    def test_mobile_shell_fills_lvh_not_dvh(self):
        mobile = self._mobile()
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("display: flex;", shell)
        self.assertIn("height: 100lvh;", shell)
        self.assertIn("max-height: none;", shell)
        self.assertNotIn("height: 100dvh;", shell)
        self.assertNotIn("max-height: 100dvh;", shell)
        self.assertNotIn("position: fixed;", shell)
        self.assertNotIn("--vvh", shell)

    def test_html_body_locked_to_lvh_when_shell_present(self):
        mobile = self._mobile()
        self.assertIn("html:has(.shell)", mobile)
        block = mobile.split("html:has(.shell)", 1)[1].split(".shell {", 1)[0]
        self.assertIn("height: 100lvh;", block)
        self.assertIn("overflow: hidden;", block)

    def test_mobile_main_unsets_desktop_dvh_max_height(self):
        mobile = self._mobile()
        main = mobile.split("  .main {", 1)[1].split("  .main-body", 1)[0]
        self.assertIn("max-height: none;", main)
        self.assertNotIn("max-height: 100dvh;", main)
        self.assertIn("overscroll-behavior-y: contain;", main)

    def test_mobile_sticky_footer_like_v8212(self):
        mobile = self._mobile()
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

    def test_no_transparent_shell_sampling_hack(self):
        mobile = self._mobile()
        self.assertNotIn("html.ios-safari .shell", mobile)
        html = BASE.read_text(encoding="utf-8")
        self.assertIn("ios-safari", html)
        self.assertIn('id="meta-theme-color"', html)

    def test_service_worker_network_first_panel_assets(self):
        pwa = PWA.read_text(encoding="utf-8")
        self.assertIn("pgclock-shell-v6", pwa)
        self.assertIn("isVersionedPanelAsset", pwa)
        self.assertNotIn("'/static/panel.css'", pwa.split("PRECACHE")[1].split("];", 1)[0])


if __name__ == "__main__":
    unittest.main()
