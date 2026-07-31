"""PasarGuard title→content gap matches bot panel (3.1.7).

Tabs sit above the page title so the title-to-content margin equals
bot list pages (.page-head → content), not title + tabs + content.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")


class PgTitleContentGapTests(unittest.TestCase):
    def test_pg_head_defers_gap_to_page_head(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".pg-head {\n  margin-bottom: 0;\n}", css)
        self.assertIn(".pg-head > .page-head {\n  margin-bottom: var(--space-4);\n}", css)
        self.assertIn(
            ".pg-head > .pg-tabs,\n.pg-head > .section-tabs {\n  margin-bottom: 8px;\n}",
            css,
        )
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn(".pg-head { margin-bottom: 0; }", mobile)
        self.assertIn(".pg-head > .page-head { margin-bottom: var(--space-3); }", mobile)

    def test_all_pg_pages_put_tabs_above_title(self):
        pages = sorted(Path("app/web/templates").glob("pg_*.html"))
        self.assertTrue(pages)
        for path in pages:
            src = path.read_text(encoding="utf-8")
            self.assertIn('class="pg-head"', src, msg=path.name)
            head = src.split('class="pg-head"', 1)[1]
            # Close of pg-head is before first major content block
            head_only = re.split(
                r'<div class="card|<div class="stats-grid|<div class="flash|<div class="pg-admin-head|{%\s*if\s+not\s+is_admin',
                head,
                maxsplit=1,
            )[0]
            tabs_at = head_only.find("pg_tabs(")
            title_at = head_only.find('class="page-head"')
            self.assertGreaterEqual(tabs_at, 0, msg=path.name)
            self.assertGreaterEqual(title_at, 0, msg=path.name)
            self.assertLess(tabs_at, title_at, msg=f"{path.name}: tabs must be above title")


if __name__ == "__main__":
    unittest.main()
