"""Solid bot/PG chrome + safe speed hooks (no gradient borders / title underlines)."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ChromeSolidTests(unittest.TestCase):
    def test_no_gradient_chrome_tokens(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        for dead in (
            "--bot-border-grad",
            "--pg-border-grad",
            "--bot-title-grad",
            "--pg-title-grad",
            "--bot-edge",
            "--pg-edge",
            ".page-title::after",
            ".ui-modal-head::after",
        ):
            self.assertNotIn(dead, css)
        self.assertIn("--bot-line", css)
        self.assertIn("--pg-line", css)
        self.assertIn("--bot-fill", css)
        self.assertIn("--pg-fill", css)

    def test_sidebar_selector_uses_section_fill(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".nav-item-bot.active,\n.nav-item-bot.active:hover {\n  background: var(--bot-fill);", css)
        self.assertIn(".nav-item-pg.active,\n.nav-item-pg.active:hover {\n  background: var(--pg-fill);", css)
        self.assertIn(".nav-section-bot .nav-ico { color: var(--bot-line); }", css)
        self.assertIn(".nav-section-pg .nav-ico { color: var(--pg-line); }", css)

    def test_menu_toggle_transparent(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        # Extract .menu-toggle block
        block = css.split(".menu-toggle {", 1)[1].split("}", 1)[0]
        self.assertIn("background: transparent;", block)

    def test_gift_codes_modal_recent_title(self):
        plans = (ROOT / "app/web/templates/plans.html").read_text(encoding="utf-8")
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn('class="gift-codes-recent-title"', plans)
        self.assertNotIn('style="margin-top:var(--space-3)"', plans)
        self.assertIn(".gift-codes-recent-title", css)

    def test_macros_page_title_no_tone_class(self):
        macros = (ROOT / "app/web/templates/macros.html").read_text(encoding="utf-8")
        self.assertNotIn("page-title--{{ tone }}", macros)
        self.assertIn('<div class="page-title">', macros)

    def test_no_pulse_items_jinja_trap(self):
        home = (ROOT / "app/web/templates/home.html").read_text(encoding="utf-8")
        reseller = (ROOT / "app/web/templates/reseller_home.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("pulse.items", home)
        self.assertNotIn("pulse.items", reseller)


class SafeSpeedHooksTests(unittest.TestCase):
    def test_gzip_self_hosted_fonts_and_caches(self):
        api = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("GZipMiddleware", api)
        self.assertIn("font-src 'self' data:", api)
        self.assertNotIn("fonts.googleapis.com", api)
        self.assertIn("peek_sidebar_counts", api)
        base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
        self.assertIn("/static/fonts.css", base)
        self.assertNotIn("fonts.googleapis.com", base)
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertNotIn("X-Panel-Nav", js)
        self.assertNotIn("panelNavigate", js)


if __name__ == "__main__":
    unittest.main()
