"""Mobile shell uses measured --vvh; sidebar absolute inside shell."""

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

    def test_mobile_shell_uses_measured_vvh(self):
        mobile = self._mobile()
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("height: var(--vvh, 100dvh);", shell)
        self.assertIn("position: relative;", shell)
        self.assertNotIn("height: 100lvh;", shell)

    def test_sidebar_absolute_not_fixed_calc(self):
        mobile = self._mobile()
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("position: absolute;", side)
        self.assertIn("top: 0;", side)
        self.assertIn("bottom: 0;", side)
        self.assertNotIn("position: fixed;", side)
        self.assertNotIn("100dvh - var(--topbar-h)", side)

    def test_vvh_script_in_head_before_css(self):
        base = BASE.read_text(encoding="utf-8")
        script_pos = base.index("setProperty(\"--vvh\"")
        css_pos = base.index("panel.css")
        self.assertLess(script_pos, css_pos)

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

    def test_theme_color_not_transparent_on_ios(self):
        base = BASE.read_text(encoding="utf-8")
        self.assertNotIn('"transparent"', base)

    def test_service_worker_network_first_panel_assets(self):
        pwa = PWA.read_text(encoding="utf-8")
        self.assertIn("pgclock-shell-v14", pwa)
        self.assertIn("isVersionedPanelAsset", pwa)


if __name__ == "__main__":
    unittest.main()
