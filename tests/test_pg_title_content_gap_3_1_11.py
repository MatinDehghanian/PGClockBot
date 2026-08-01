"""PG title gap root fix — bot-identical chrome (updated for 3.2.14)."""

from __future__ import annotations

import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")


class PgTitleContentGapRootTests(unittest.TestCase):
    def test_page_head_gap_token(self):
        css = CSS.read_text(encoding="utf-8")
        bot = css.split(".page-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--page-title-gap);", bot)

    def test_page_head_actions_do_not_wrap_under_title(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(
            ".page-head:has(> .actions),\n.page-head:has(> .btn) {\n  flex-wrap: nowrap;\n}",
            css,
        )
        title_wrap = css.split(".page-head > div:has(> .page-title) {\n", 1)[1].split("}", 1)[0]
        self.assertIn("flex: 1 1 0%;", title_wrap)

    def test_flush_search_top_pad_is_not_card_pad(self):
        css = CSS.read_text(encoding="utf-8")
        block = css.split(".card.card-flush > .search-bar {\n", 1)[1].split("}", 1)[0]
        self.assertIn("padding: var(--space-1) var(--card-pad) 0;", block)
        self.assertNotIn("padding: var(--card-pad) var(--card-pad) 0;", block)

    def test_pg_pages_match_bot_chrome(self):
        pages = sorted(Path("app/web/templates").glob("pg_*.html"))
        self.assertTrue(pages)
        for path in pages:
            src = path.read_text(encoding="utf-8")
            self.assertNotIn('class="pg-head"', src, msg=path.name)
            self.assertNotIn("pg_tabs(", src, msg=path.name)


if __name__ == "__main__":
    unittest.main()
