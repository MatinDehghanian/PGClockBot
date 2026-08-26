"""Mobile shell — v8.2.12 layout (100dvh) with minimal Safari 26 sampling guard."""

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

    def test_mobile_shell_uses_dvh_not_lvh_overlay_hacks(self):
        mobile = self._mobile()
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("display: flex;", shell)
        self.assertIn("height: 100dvh;", shell)
        self.assertIn("max-height: 100dvh;", shell)
        self.assertNotIn("height: 100lvh;", shell)
        self.assertNotIn("max-height: none;", shell)
        self.assertNotIn("--safari-overlay", shell)
        self.assertNotIn("--vvh", shell)
        self.assertIn("overflow: hidden;", shell)
        self.assertIn("padding-top: calc(var(--topbar-h) + var(--safe-top));", shell)

    def test_no_document_lock_or_safari_overlay_variable(self):
        mobile = self._mobile()
        self.assertNotIn("html:has(.shell)", mobile)
        self.assertNotIn("100lvh - 100svh", mobile)
        self.assertNotIn("100lvh - 100dvh", mobile)
        for line in mobile.splitlines():
            stripped = line.strip()
            if stripped.startswith("/*") or stripped.startswith("*"):
                continue
            self.assertNotIn("--safari-overlay", stripped)

    def test_mobile_main_is_inner_scroller(self):
        mobile = self._mobile()
        main = mobile.split("  .main {", 1)[1].split("  .main-body", 1)[0]
        self.assertIn("overflow-y: auto;", main)
        self.assertIn("overscroll-behavior-y: auto;", main)
        self.assertIn("min-height: 0;", main)
        self.assertNotIn("--safari-overlay", main)
        self.assertNotIn(".main::after", main)
        self.assertIn(
            "padding: var(--page-title-gap) var(--space-2) calc(var(--page-title-gap) + var(--safe-bottom));",
            main,
        )

    def test_mobile_sticky_footer(self):
        mobile = self._mobile()
        self.assertIn(".main-body { flex: 1 0 auto;", mobile)
        footer = mobile.split("  .site-footer {", 1)[1].split("  .footer-meta", 1)[0]
        self.assertIn("margin-top: auto;", footer)

    def test_ios_safari_sampling_guard_without_layout_hacks(self):
        mobile = self._mobile()
        self.assertIn("html.ios-safari .shell", mobile)
        self.assertIn("html.ios-safari .main", mobile)
        self.assertIn("html.ios-safari .side:not(.open)", mobile)
        self.assertNotIn(".side:not(.open) {", mobile)

    def test_auth_wrap_uses_dvh(self):
        css = CSS.read_text(encoding="utf-8")
        auth = css.split(".auth-wrap {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: 100dvh;", auth)
        self.assertNotIn("100lvh - 100svh", auth)

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
        self.assertNotIn("'/static/panel.css'", pwa.split("PRECACHE")[1].split("];", 1)[0])


if __name__ == "__main__":
    unittest.main()
