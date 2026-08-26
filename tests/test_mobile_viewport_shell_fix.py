"""Mobile shell fills 100lvh; inner .main scrolls; no page-loading hacks."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
BASE = ROOT / "app/web/templates/base.html"
JS = ROOT / "app/web/static/panel.js"
PWA = ROOT / "app/services/pwa.py"
DEFER = ROOT / "app/web/templates/_panel_widgets_defer.html"


class MobileViewportShellFixTests(unittest.TestCase):
    def _mobile(self) -> str:
        return CSS.read_text(encoding="utf-8").split("@media (max-width: 900px)", 1)[1]

    def test_mobile_shell_fills_lvh_not_dvh_cap(self):
        mobile = self._mobile()
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("height: 100lvh;", shell)
        self.assertIn("min-height: 100lvh;", shell)
        self.assertIn("max-height: none;", shell)
        self.assertNotIn("max-height: 100dvh;", shell)
        self.assertNotIn("--safari-overlay", shell)

    def test_document_locked_for_inner_scroll(self):
        mobile = self._mobile()
        self.assertIn("html:has(.shell)", mobile)
        block = mobile.split("html:has(.shell)", 1)[1].split(".shell {", 1)[0]
        self.assertIn("overflow: hidden;", block)
        self.assertIn("100lvh", block)
        self.assertNotIn("100lvh - 100svh", mobile)

    def test_mobile_main_is_inner_scroller(self):
        mobile = self._mobile()
        main = mobile.split("  .main {", 1)[1].split("  .main-body", 1)[0]
        self.assertIn("overflow-y: auto;", main)
        self.assertIn("max-height: none;", main)
        self.assertIn(
            "padding: var(--page-title-gap) var(--space-2) calc(var(--foot-gap) + var(--safe-bottom));",
            main,
        )

    def test_no_page_loading_system(self):
        base = BASE.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        defer = DEFER.read_text(encoding="utf-8")
        self.assertNotIn("page-load-veil", base)
        self.assertNotIn("page-skeleton", base)
        self.assertNotIn("page-loading", base)
        self.assertNotIn("page-loading", js)
        self.assertNotIn("armVeil", defer)
        self.assertNotIn(".page-load-veil", css)
        self.assertNotIn("html.page-loading", css)

    def test_ios_safari_sampling_guard_only(self):
        mobile = self._mobile()
        self.assertIn("html.ios-safari .side:not(.open)", mobile)
        self.assertNotIn(".side:not(.open) {", mobile)

    def test_service_worker_network_first_panel_assets(self):
        pwa = PWA.read_text(encoding="utf-8")
        self.assertIn("pgclock-shell-v12", pwa)
        self.assertIn("isVersionedPanelAsset", pwa)


if __name__ == "__main__":
    unittest.main()
