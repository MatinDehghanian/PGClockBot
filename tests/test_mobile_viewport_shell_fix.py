"""Mobile shell uses v8.2.8 geometry; no page-loading hacks."""

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

    def test_mobile_shell_uses_dvh_like_v828(self):
        mobile = self._mobile()
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("height: 100dvh;", shell)
        self.assertIn("max-height: 100dvh;", shell)
        self.assertNotIn("height: 100lvh;", shell)
        self.assertNotIn("--safari-overlay", shell)

    def test_no_document_lock_on_html_body(self):
        mobile = self._mobile()
        self.assertNotIn("html:has(.shell)", mobile)

    def test_mobile_main_is_inner_scroller(self):
        mobile = self._mobile()
        main = mobile.split("  .main {", 1)[1].split("  .main-body", 1)[0]
        self.assertIn("overflow-y: auto;", main)
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

    def test_no_ios_safari_layout_hacks(self):
        mobile = self._mobile()
        self.assertNotIn("html.ios-safari .shell", mobile)
        self.assertNotIn("height: 0 !important;", mobile)

    def test_service_worker_network_first_panel_assets(self):
        pwa = PWA.read_text(encoding="utf-8")
        self.assertIn("pgclock-shell-v13", pwa)
        self.assertIn("isVersionedPanelAsset", pwa)


if __name__ == "__main__":
    unittest.main()
