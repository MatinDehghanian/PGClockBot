"""Mobile shell — document scroll, stable svh min-height, no nested main scroller."""

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

    def test_mobile_shell_content_flow_not_viewport_stretch(self):
        mobile = self._mobile()
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        side = mobile.split("  .side {", 1)[1].split("  .side.open", 1)[0]
        closed = mobile.split(".side:not(.open)", 1)[1][:200]
        self.assertIn("height: auto;", shell)
        self.assertNotIn("flex: 1 0 auto;", shell)
        self.assertIn("padding-bottom: var(--safe-bottom);", side)
        self.assertNotIn("var(--foot-gap) + var(--safe-bottom)", side)
        self.assertIn("height: 0;", closed)
        shell_block = shell.split("}", 1)[0]
        for unit in ("100dvh", "100svh", "100lvh", "100vh", "var(--vvh"):
            self.assertNotIn(unit, shell_block)
        self.assertIn("padding-bottom: var(--safe-bottom);", shell)

    def test_document_is_scroll_owner(self):
        mobile = self._mobile()
        doc = mobile.split("html:has(.shell)", 1)[1].split(".shell {", 1)[0]
        main = mobile.split("  .main {", 1)[1].split("  .main-body", 1)[0]
        self.assertIn("overflow-y: auto;", doc)
        self.assertIn("overflow: visible;", main)
        self.assertNotIn("overflow-y: auto;", main)

    def test_sidebar_fixed_with_pointer_events_guard(self):
        mobile = self._mobile()
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("position: fixed;", side)
        self.assertIn("bottom: 0;", side)
        self.assertIn("pointer-events: none;", mobile.split(".side:not(.open)", 1)[1][:120])

    def test_no_vvh_script(self):
        base = BASE.read_text(encoding="utf-8")
        self.assertNotIn("--vvh", base)

    def test_no_page_loading_system(self):
        base = BASE.read_text(encoding="utf-8")
        defer = DEFER.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        self.assertNotIn("page-load-veil", base)
        self.assertNotIn("armVeil", defer)
        self.assertNotIn(".page-load-veil", css)

    def test_hamburger_pageshow_reset(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("addEventListener('pageshow'", js)
        self.assertIn("stopPropagation", js)

    def test_no_ios_safari_layout_hacks(self):
        mobile = self._mobile()
        self.assertNotIn("html.ios-safari .shell", mobile)
        self.assertNotIn("--safari-overlay", mobile)

    def test_service_worker_cache(self):
        pwa = PWA.read_text(encoding="utf-8")
        self.assertIn("pgclock-shell-v19", pwa)


if __name__ == "__main__":
    unittest.main()
