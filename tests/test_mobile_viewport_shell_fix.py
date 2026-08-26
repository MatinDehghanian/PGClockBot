"""Mobile shell uses 100svh + collapsed closed drawer (Safari glass / no black bar)."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
BASE = ROOT / "app/web/templates/base.html"
JS = ROOT / "app/web/static/panel.js"
PWA = ROOT / "app/services/pwa.py"


class MobileViewportShellFixTests(unittest.TestCase):
    def test_mobile_shell_uses_svh_not_dvh(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("height: 100svh;", shell)
        self.assertIn("max-height: 100svh;", shell)
        self.assertNotIn("height: 100dvh;", shell)
        self.assertNotIn("position: fixed;", shell)

    def test_closed_side_collapses_off_bottom_edge(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn(".side:not(.open)", mobile)
        closed = mobile.split(".side:not(.open) {", 1)[1].split("}", 1)[0]
        self.assertIn("height: 0 !important;", closed)
        self.assertIn("visibility: hidden;", closed)

    def test_ios_safari_no_full_bleed_dark_under_toolbar(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn("html.ios-safari .shell,", mobile)
        self.assertIn("html.ios-safari .main", mobile)
        block = mobile.split("html.ios-safari .shell,", 1)[1].split("  .main {", 1)[0]
        self.assertIn("background: transparent;", block)
        self.assertNotIn("background: var(--background);", block)

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
        mobile = css.split("@media (max-width: 640px)", 1)[1]
        self.assertNotIn(".home-action-item {\n    align-items: flex-start;", mobile)

    def test_service_worker_network_first_panel_assets(self):
        pwa = PWA.read_text(encoding="utf-8")
        self.assertIn("pgclock-shell-v6", pwa)
        self.assertIn("isVersionedPanelAsset", pwa)

    def test_base_ios_safari_theme_transparent(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertIn("ios-safari", html)
        self.assertIn('id="meta-theme-color"', html)
        self.assertNotIn("--vvh", html)


if __name__ == "__main__":
    unittest.main()
