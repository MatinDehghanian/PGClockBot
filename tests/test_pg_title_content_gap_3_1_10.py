"""PG title gap — bot-identical chrome (updated for 3.2.14)."""

from __future__ import annotations

import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")


class PgTitleContentGapTests(unittest.TestCase):
    def test_page_head_owns_gap_for_bot_and_pg(self):
        css = CSS.read_text(encoding="utf-8")
        bot = css.split(".page-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--page-title-gap);", bot)

    def test_pg_pages_have_no_pg_head_or_tabs(self):
        pages = sorted(Path("app/web/templates").glob("pg_*.html"))
        self.assertTrue(pages)
        for path in pages:
            src = path.read_text(encoding="utf-8")
            self.assertNotIn('class="pg-head"', src, msg=path.name)
            self.assertNotIn("pg_tabs(", src, msg=path.name)
            self.assertIn('class="page-head"', src, msg=path.name)


if __name__ == "__main__":
    unittest.main()
