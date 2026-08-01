"""PasarGuard title→content gap — root-cause fix (3.1.11 / corrected 3.2.13).

Title first like bot; .pg-head owns a single --page-title-gap below the
header stack; tabs→title gap is --space-1 only; no negative pull-up.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")


class PgTitleContentGapRootTests(unittest.TestCase):
    def test_pg_head_owns_the_same_gap_token_as_bot(self):
        css = CSS.read_text(encoding="utf-8")
        bot = css.split(".page-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--page-title-gap);", bot)

        pg = css.split(".pg-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--page-title-gap);", pg)
        self.assertIn("flex-direction: column;", pg)
        self.assertIn("gap: var(--space-1);", pg)
        self.assertNotIn("gap: var(--page-title-gap);", pg)
        self.assertIn("margin-top: 0;", pg)
        self.assertNotIn("margin-top: calc(", pg)

        self.assertIn(".pg-head > .page-head {\n  margin-bottom: 0;\n}", css)
        self.assertIn(
            ".pg-head > .pg-tabs,\n.pg-head > .section-tabs {\n  margin-bottom: 0;\n  padding-bottom: 0;\n}",
            css,
        )

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

    def test_all_pg_pages_put_title_before_tabs(self):
        pages = sorted(Path("app/web/templates").glob("pg_*.html"))
        self.assertTrue(pages)
        for path in pages:
            src = path.read_text(encoding="utf-8")
            head = src.split('class="pg-head"', 1)[1]
            head_only = re.split(
                r'<div class="card|<div class="home-panels|<div class="stats-grid|<div class="flash|<div class="pg-admin-head|{%\s*if\s+not\s+is_admin',
                head,
                maxsplit=1,
            )[0]
            tabs_at = head_only.find("pg_tabs(")
            title_at = head_only.find('class="page-head"')
            self.assertLess(title_at, tabs_at, msg=f"{path.name}: title must be before tabs")


if __name__ == "__main__":
    unittest.main()
