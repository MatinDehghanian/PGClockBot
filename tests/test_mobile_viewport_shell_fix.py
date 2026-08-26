"""Mobile shell fills 100lvh; inner .main scrolls; no svh overlay inset."""

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

    def test_mobile_shell_fills_lvh_not_dvh_or_svh(self):
        mobile = self._mobile()
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("display: flex;", shell)
        self.assertIn("height: 100lvh;", shell)
        self.assertIn("min-height: 100lvh;", shell)
        self.assertIn("max-height: none;", shell)
        self.assertNotIn("height: 100dvh;", shell)
        self.assertNotIn("max-height: 100dvh;", shell)
        self.assertNotIn("height: 100svh;", shell)
        self.assertNotIn("max-height: 100svh;", shell)
        self.assertNotIn("position: fixed;", shell)
        self.assertNotIn("--vvh", shell)
        self.assertIn("overflow: hidden;", shell)

    def test_html_body_locked_to_lvh_no_overlay_inset(self):
        mobile = self._mobile()
        self.assertIn("html:has(.shell)", mobile)
        block = mobile.split("html:has(.shell)", 1)[1].split(".shell {", 1)[0]
        self.assertIn("min-height: 100lvh;", block)
        self.assertIn("overflow: hidden;", block)
        self.assertNotIn("--safari-overlay", block)
        self.assertNotIn("100lvh - 100svh", block)
        self.assertNotIn("100lvh - 100dvh", block)

    def test_mobile_main_is_inner_scroller_not_document(self):
        mobile = self._mobile()
        main = mobile.split("  .main {", 1)[1].split("  .main-body", 1)[0]
        self.assertIn("max-height: none;", main)
        self.assertNotIn("max-height: 100dvh;", main)
        self.assertIn("overflow-y: auto;", main)
        self.assertIn("overscroll-behavior-y: auto;", main)
        self.assertNotIn("--safari-overlay", main)
        self.assertIn(".main::after", main)
        self.assertIn("flex: 0 0 1px;", main)
        self.assertIn(
            "padding: var(--page-title-gap) var(--space-2) calc(var(--page-title-gap) + var(--safe-bottom));",
            main,
        )

    def test_mobile_sticky_footer_like_v8212(self):
        mobile = self._mobile()
        self.assertIn(".main-body { flex: 1 0 auto;", mobile)
        footer = mobile.split("  .site-footer {", 1)[1].split("  .footer-meta", 1)[0]
        self.assertIn("margin-top: auto;", footer)

    def test_no_transparent_shell_sampling_hack(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertNotIn("html.ios-safari .shell", css)
        self.assertNotIn("html.ios-safari .main {", css)
        html = BASE.read_text(encoding="utf-8")
        self.assertIn("ios-safari", html)
        self.assertIn('id="meta-theme-color"', html)
        self.assertNotIn("--vvh", html)

    def test_auth_wrap_uses_lvh(self):
        css = CSS.read_text(encoding="utf-8")
        auth = css.split(".auth-wrap {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: 100lvh;", auth)
        self.assertNotIn("min-height: 100dvh;", auth)
        self.assertNotIn("100lvh - 100svh", auth)
        self.assertNotIn("100lvh - 100dvh", auth)

    def test_users_table_polish_restored(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".cell-name-tags", css)
        self.assertIn(".users-svc-name", css)
        self.assertIn(".ui-select-menu.users-svc-boxed", css)
        self.assertIn(".users-svc-ui.ui-select", css)
        js = JS.read_text(encoding="utf-8")
        self.assertIn("users-svc-ui", js)
        self.assertIn("users-svc-boxed", js)
        self.assertIn("syncUsersSvcToggleAlert", js)

    def test_action_items_vertically_centered(self):
        css = CSS.read_text(encoding="utf-8")
        leading = css.split(".home-action-leading {", 1)[1].split("}", 1)[0]
        self.assertIn("align-items: center;", leading)

    def test_no_viewport_hack_scripts(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertNotIn("--vvh", html)
        self.assertNotIn("visualViewport", html)
        js = JS.read_text(encoding="utf-8")
        self.assertNotIn("__pgSetVVH", js)
        self.assertNotIn("visualViewport", js)

    def test_service_worker_network_first_panel_assets(self):
        pwa = PWA.read_text(encoding="utf-8")
        self.assertIn("pgclock-shell-v10", pwa)
        self.assertIn("isVersionedPanelAsset", pwa)
        self.assertIn("/static/fonts.css", pwa)
        self.assertIn("/static/fonts/", pwa)
        self.assertNotIn("self.clients.claim()", pwa)
        self.assertNotIn("'/static/panel.css'", pwa.split("PRECACHE")[1].split("];", 1)[0])


if __name__ == "__main__":
    unittest.main()
