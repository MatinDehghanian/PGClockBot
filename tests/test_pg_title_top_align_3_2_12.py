"""3.2.12 — PG title box Y aligns with bot (above + below parity).

Tabs stay ABOVE the title (so title→content = --page-title-gap like bot).
.pg-head pulls up by (tab row + tabs→title gap) into .main’s top padding
so the icon+title box starts at the same Y as bot titles.

Do NOT regress by:
- removing the pull-up (title drops below bot)
- putting tabs between title and content
- changing .main padding-top / icon / title size
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"


class PgTitleTopAlign3212Tests(unittest.TestCase):
    def test_pg_head_pulls_up_to_align_title_with_bot(self):
        css = CSS.read_text(encoding="utf-8")
        pg = css.split(".pg-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn(
            "margin-top: calc(-1 * (var(--btn-h) + var(--space-1)));",
            pg,
        )
        self.assertIn("margin-bottom: var(--page-title-gap);", pg)
        self.assertIn("gap: var(--space-1);", pg)
        # .main top pad unchanged (bot + PG share it)
        main = css.split(".main {\n", 1)[1]
        self.assertIn(
            "padding: var(--page-title-gap) var(--space-4) calc(var(--page-title-gap) + var(--safe-bottom));",
            main,
        )
        ico = css.split(".page-title-ico {\n", 1)[1].split("}", 1)[0]
        self.assertIn("width: 40px;", ico)
        self.assertIn("height: 40px;", ico)

    def test_mobile_same_pull_up(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        block = mobile.split(".pg-head {", 1)[1].split("}", 1)[0]
        self.assertIn(
            "margin-top: calc(-1 * (var(--btn-h) + var(--space-1)));",
            block,
        )
        self.assertIn("margin-bottom: var(--page-title-gap);", block)
        self.assertIn("gap: var(--space-1);", block)

    def test_tabs_still_above_title(self):
        pages = sorted((ROOT / "app/web/templates").glob("pg_*.html"))
        self.assertEqual(len(pages), 8)
        for path in pages:
            src = path.read_text(encoding="utf-8")
            head = src.split('class="pg-head"', 1)[1]
            head_only = re.split(
                r'<div class="card|<div class="home-panels|<div class="stats-grid|<div class="flash|<div class="pg-admin-head|{%\s*if\s+not\s+is_admin',
                head,
                maxsplit=1,
            )[0]
            self.assertLess(
                head_only.find("pg_tabs("),
                head_only.find('class="page-head"'),
                msg=path.name,
            )


if __name__ == "__main__":
    unittest.main()
