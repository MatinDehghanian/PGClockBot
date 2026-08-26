"""Mobile shell — v8.2.8 geometry + root-cause bottom-gap fix."""

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

    def test_mobile_shell_v828_dvh(self):
        mobile = self._mobile()
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("height: 100dvh;", shell)
        self.assertNotIn("var(--vvh", shell)
        self.assertIn("padding-bottom: var(--safe-bottom);", shell)

    def test_sidebar_fixed_with_pointer_events_guard(self):
        mobile = self._mobile()
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("position: fixed;", side)
        self.assertIn("bottom: 0;", side)
        self.assertIn("pointer-events: none;", mobile.split(".side:not(.open)", 1)[1][:120])

    def test_mobile_main_is_inner_scroller(self):
        mobile = self._mobile()
        main = mobile.split("  .main {", 1)[1].split("  .main-body", 1)[0]
        self.assertIn("overflow-y: auto;", main)
        self.assertIn("height: auto;", main)
        self.assertIn("max-height: none;", main)
        self.assertIn("flex: 1 1 0;", main)
        self.assertIn("padding: var(--page-title-gap) var(--space-2) var(--foot-gap);", main)
        self.assertNotIn("calc(var(--foot-gap) + var(--safe-bottom))", main)

    def test_no_vvh_script(self):
        base = BASE.read_text(encoding="utf-8")
        self.assertNotIn("--vvh", base)

    def test_no_page_loading_system(self):
        base = BASE.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        defer = DEFER.read_text(encoding="utf-8")
        self.assertNotIn("page-load-veil", base)
        self.assertNotIn("page-skeleton", base)
        self.assertNotIn("page-loading", base)
        self.assertNotIn("armVeil", defer)
        self.assertNotIn(".page-load-veil", css)

    def test_hamburger_pageshow_reset(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("addEventListener('pageshow'", js)
        self.assertIn("stopPropagation", js)

    def test_no_ios_safari_layout_hacks(self):
        mobile = self._mobile()
        self.assertNotIn("html.ios-safari .shell", mobile)
        side = mobile.split("  .side {", 1)[1].split("  .side.open", 1)[0]
        self.assertNotIn("height: 0", side)

    def test_service_worker_cache(self):
        pwa = PWA.read_text(encoding="utf-8")
        self.assertIn("pgclock-shell-v16", pwa)


if __name__ == "__main__":
    unittest.main()
