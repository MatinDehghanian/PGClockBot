"""Chrome polish (bot/PG neutral fills + gradient edges) and safe speed hooks."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ChromePolishTests(unittest.TestCase):
    def test_bot_pg_sections_use_gradient_border_not_tint_fill(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn("--bot-border-grad", css)
        self.assertIn("--pg-border-grad", css)
        # Neutral fill via padding-box gradient, not orange/blue wash on section.
        self.assertIn(
            "linear-gradient(var(--bg-card), var(--bg-card)) padding-box",
            css,
        )
        self.assertIn("var(--bot-border-grad) border-box", css)
        self.assertIn("var(--pg-border-grad) border-box", css)
        self.assertNotIn(
            "background: color-mix(in srgb, #e08a3c 12%, transparent);",
            css,
        )
        self.assertNotIn(
            "background: color-mix(in srgb, #3d8fd1 12%, transparent);",
            css,
        )

    def test_page_and_modal_titles_have_accent(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        macros = (ROOT / "app/web/templates/macros.html").read_text(encoding="utf-8")
        self.assertIn("page-title--{{ tone }}", macros)
        self.assertIn(".page-title::after", css)
        self.assertIn(".ui-modal-head::after", css)
        self.assertIn("padding: var(--space-3);", css)

    def test_no_pulse_items_jinja_trap(self):
        """Guard the 7.0.3 dashboard 500: pulse.items is dict.items in Jinja."""
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
        self.assertTrue(
            (ROOT / "app/web/static/fonts/Vazirmatn-Variable.woff2").is_file()
        )
        pg = (ROOT / "app/services/pasarguard.py").read_text(encoding="utf-8")
        self.assertIn("_read_cache_ident", pg)
        self.assertIn("cache_get", pg)
        # Content-swap nav caused wrong sidebar active — must stay off.
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertNotIn("X-Panel-Nav", js)
        self.assertNotIn("panelNavigate", js)


if __name__ == "__main__":
    unittest.main()
