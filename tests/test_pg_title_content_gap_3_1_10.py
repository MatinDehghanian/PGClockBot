"""PasarGuard title→content gap — align with bot (3.1.10 / corrected 3.2.13).

Title FIRST at the same Y as bot (.main --page-title-gap).
Tabs tight under title. One --page-title-gap under the whole header.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")


class PgTitleContentGapTests(unittest.TestCase):
    def test_pg_title_to_content_uses_same_token_as_bot(self):
        css = CSS.read_text(encoding="utf-8")
        bot = css.split(".page-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--page-title-gap);", bot)
        pg = css.split(".pg-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--page-title-gap);", pg)
        self.assertIn("gap: var(--space-1);", pg)
        self.assertNotIn("gap: var(--page-title-gap);", pg)
        self.assertIn("margin-top: 0;", pg)
        self.assertNotIn("margin-top: calc(", pg)
        self.assertIn(".pg-head > .page-head {\n  margin-bottom: 0;\n}", css)
        self.assertNotIn(
            ".pg-head > .pg-tabs,\n.pg-head > .section-tabs {\n  margin-bottom: var(--section-gap);\n}",
            css,
        )

    def test_all_pg_pages_put_title_before_tabs(self):
        pages = sorted(Path("app/web/templates").glob("pg_*.html"))
        self.assertTrue(pages)
        for path in pages:
            src = path.read_text(encoding="utf-8")
            self.assertIn('class="pg-head"', src, msg=path.name)
            head = src.split('class="pg-head"', 1)[1]
            head_only = re.split(
                r'<div class="card|<div class="home-panels|<div class="stats-grid|<div class="flash|<div class="pg-admin-head|{%\s*if\s+not\s+is_admin',
                head,
                maxsplit=1,
            )[0]
            tabs_at = head_only.find("pg_tabs(")
            title_at = head_only.find('class="page-head"')
            self.assertGreaterEqual(tabs_at, 0, msg=path.name)
            self.assertGreaterEqual(title_at, 0, msg=path.name)
            self.assertLess(title_at, tabs_at, msg=f"{path.name}: title must be before tabs")


if __name__ == "__main__":
    unittest.main()
