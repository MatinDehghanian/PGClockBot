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
        foot = mobile.split(".side .side-foot", 1)[1][:240]
        self.assertIn("padding-bottom: var(--bottom-inset);", foot)
        self.assertNotIn("var(--foot-gap) + var(--safe-bottom)", side)
        closed = mobile.split(".side:not(.open)", 1)[1][:160]
        self.assertNotIn("height: 0;", closed)
        shell_block = shell.split("}", 1)[0]
        # shell may use min-height:100svh but must not lock height to a viewport unit
        for unit in ("100dvh", "100lvh", "100vh", "var(--vvh"):
            self.assertNotIn(f"height: {unit}", shell_block)
            self.assertNotIn(f"height:{unit}", shell_block)
        self.assertIn("padding-bottom: 0;", shell)
        self.assertIn("min-height: 100svh;", shell_block)

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
        self.assertIn("padding: var(--page-title-gap) var(--space-2) 0;", main)

    def test_sidebar_fixed_with_pointer_events_guard(self):
        mobile = self._mobile()
        side = mobile.split("  .side {", 1)[1].split("  .side.open", 1)[0]
        self.assertIn("position: fixed;", side)
        self.assertIn("bottom: 0;", side)
        self.assertIn("pointer-events: none;", mobile.split(".side:not(.open)", 1)[1][:120])

    def test_bottom_inset_token_and_shared_footers(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("--bottom-inset:", css[:5000])
        self.assertIn("--footer-bar-h:", css[:5000])
        mobile = self._mobile()
        site = mobile.split("  .site-footer {", 1)[1].split("  .footer-meta", 1)[0]
        side_foot = mobile.split(".side .side-foot", 1)[1][:280]
        self.assertIn("padding-bottom: var(--bottom-inset);", site)
        self.assertIn("padding-bottom: var(--bottom-inset);", side_foot)
        self.assertIn("min-height: calc(var(--footer-bar-h) + var(--bottom-inset));", site)
        self.assertIn("min-height: calc(var(--footer-bar-h) + var(--bottom-inset));", side_foot)

    def test_no_vvh_or_visual_viewport_js(self):
        base = BASE.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        self.assertNotIn("--vvh", base)
        self.assertNotIn("visualViewport", base)
        self.assertNotIn("visualViewport", js)

    def test_sw_fallback_ignores_query_for_panel_assets(self):
        sw = PWA.read_text(encoding="utf-8")
        self.assertIn("pgclock-shell-v26", sw)
        self.assertIn("matchIgnoreSearch", sw)
        self.assertIn("isVersionedPanelAsset", sw)


    def test_ios_safari_liquid_glass_rules(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn("html.ios-safari .side:not(.open)", mobile)
        self.assertIn("height: 0 !important;", mobile)
        self.assertIn("html.ios-safari .side.open", mobile)
        self.assertIn("background-size: 100% calc(100% - 3px);", mobile)
        self.assertIn("backdrop-filter: blur(16px)", mobile)
        base = BASE.read_text(encoding="utf-8")
        self.assertIn('ios-safari', base)
        self.assertIn('ios-standalone', base)
        js = JS.read_text(encoding="utf-8")
        self.assertIn("ios-safari", js)


if __name__ == "__main__":
    unittest.main()
