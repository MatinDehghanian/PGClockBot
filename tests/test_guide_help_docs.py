"""Guide catalog + built static help site."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GuideCatalogTests(unittest.TestCase):
    def test_topics_have_required_fields(self):
        from app.services.guide_catalog import NAV_ORDER, TOPICS, topic

        self.assertEqual(set(NAV_ORDER), set(TOPICS))
        for tid in NAV_ORDER:
            t = topic(tid)
            assert t is not None
            self.assertTrue(t["title"])
            self.assertTrue(t["summary"])
            self.assertTrue(t["slug"])
            self.assertTrue(t["nav_group"])

    def test_help_href_default_and_external(self):
        from app.services import guide_catalog as gc

        gc.panel_help_payload.cache_clear()
        href = gc.help_href("plans")
        self.assertTrue(href.startswith("/help/plans"))

    def test_built_guide_present(self):
        guide = ROOT / "app" / "web" / "static" / "guide"
        self.assertTrue((guide / "index.html").is_file())
        self.assertTrue((guide / "plans" / "index.html").is_file())
        self.assertTrue((guide / "search-index.json").is_file())
        self.assertTrue((guide / "catalog.json").is_file())
        html = (guide / "plans" / "index.html").read_text(encoding="utf-8")
        self.assertIn("پلن‌ها", html)
        self.assertIn("guide-search", html)
        self.assertNotIn("{% for", html)

    def test_page_title_macro_has_help(self):
        macros = (ROOT / "app" / "web" / "templates" / "macros.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("page-help-btn", macros)
        self.assertIn("help=None", macros)
        plans = (ROOT / "app" / "web" / "templates" / "plans.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("help='plans'", plans)

    def test_help_mounted_in_app_factory(self):
        src = (ROOT / "app" / "api" / "app.py").read_text(encoding="utf-8")
        self.assertIn('"/help"', src)
        self.assertIn("help_docs", src)
        self.assertIn("path.startswith(\"/help\")", src)


if __name__ == "__main__":
    unittest.main()
