"""Mobile shell — v8.2.8 geometry; closed drawer ignores taps."""

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

    def test_sidebar_fixed_with_pointer_events_guard(self):
        mobile = self._mobile()
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("position: fixed;", side)
        self.assertIn("pointer-events: none;", mobile.split(".side:not(.open)", 1)[1][:120])

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
        self.assertIn('addEventListener(\'pageshow\'', js)
        self.assertIn("stopPropagation", js)

    def test_service_worker_cache(self):
        pwa = PWA.read_text(encoding="utf-8")
        self.assertIn("pgclock-shell-v15", pwa)


if __name__ == "__main__":
    unittest.main()
