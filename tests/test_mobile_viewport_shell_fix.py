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

    def test_mobile_shell_flex_fill_not_viewport_units(self):
        mobile = self._mobile()
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        side = mobile.split("  .side {", 1)[1].split("  .side.open", 1)[0]
        self.assertIn("height: auto;", shell)
        self.assertIn("flex: 1 0 auto;", shell)
        self.assertIn("padding-bottom: 0;", side)
        self.assertNotIn("transform: translateX", side)
        self.assertIn("right: calc(-1 * min(300px, 86vw) - 24px);", side)
        foot = mobile.split(".side .side-foot", 1)[1][:120]
        self.assertIn("padding-bottom: calc(var(--foot-gap) + var(--safe-bottom));", foot)
        self.assertNotIn("var(--foot-gap) + var(--safe-bottom)", side)
        closed = mobile.split(".side:not(.open)", 1)[1][:160]
        self.assertNotIn("height: 0;", closed)
        shell_block = shell.split("}", 1)[0]
        for unit in ("100dvh", "100svh", "100lvh", "100vh", "var(--vvh"):
            self.assertNotIn(unit, shell_block)
        self.assertIn("padding-bottom: var(--safe-bottom);", shell)

    def test_document_is_scroll_owner(self):
        mobile = self._mobile()
        html = mobile.split("html:has(.shell) {\n", 1)[1].split("}", 1)[0]
        body = mobile.split("html:has(.shell) body {\n", 1)[1].split("}", 1)[0]
        main = mobile.split("  .main {", 1)[1].split("  .main-body", 1)[0]
        self.assertIn("min-height: 100svh;", html)
        self.assertIn("height: auto;", html)
        self.assertNotRegex(html, r"(?m)^\s*height:\s*100%;")
        self.assertIn("overflow-x: visible;", html)
        self.assertIn("overflow-y: visible;", html)
        self.assertNotIn("overflow-x: hidden;", html)
        self.assertIn("min-height: 100svh;", body)
        self.assertIn("overflow-x: visible;", body)
        self.assertIn("overflow-y: visible;", body)
        self.assertNotIn("overflow-y: auto;", body)
        self.assertIn("overflow-x: clip;", main)
        self.assertIn("overflow-y: visible;", main)
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

    def test_no_page_loading_veil_but_nav_clock_present(self):
        base = BASE.read_text(encoding="utf-8")
        defer = DEFER.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        self.assertNotIn("page-load-veil", base)
        self.assertNotIn("armVeil", defer)
        self.assertNotIn(".page-load-veil", css)
        self.assertIn('id="panel-nav-clock"', base)
        self.assertIn(".panel-nav-clock", css)
        clock_css = css.split(".panel-nav-clock", 1)[1][:900]
        self.assertIn("pointer-events: none", clock_css)
        self.assertIn("color-mix(in srgb, var(--background", clock_css)
        self.assertNotIn("@keyframes panel-nav-clock-show", css)
        self.assertNotIn("animation: panel-nav-clock-show", css)
        self.assertIn("setTimeout(function () {", js)
        self.assertIn("clock.hidden = false", js)
        self.assertIn("void clock.offsetWidth", js)
        self.assertIn("clearTimeout(armTimer)", js)

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
        self.assertIn("pgclock-shell-v24", pwa)


if __name__ == "__main__":
    unittest.main()
