"""3.2.11 — PG title→content gap parity with bot (tabs above title).

Do NOT regress by:
- putting tabs between title and content
- stacking a second --page-title-gap as .pg-head gap
- changing page-title / icon sizes
- changing .main padding-top above titles
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"


class PgTitleContentParity3211Tests(unittest.TestCase):
    def test_title_to_content_token_parity(self):
        css = CSS.read_text(encoding="utf-8")
        bot = css.split(".page-head {\n", 1)[1].split("}", 1)[0]
        pg = css.split(".pg-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--page-title-gap);", bot)
        self.assertIn("margin-bottom: var(--page-title-gap);", pg)
        self.assertIn("gap: var(--space-1);", pg)
        self.assertNotIn("gap: var(--page-title-gap);", pg)
        # Icon / title size untouched
        ico = css.split(".page-title-ico {\n", 1)[1].split("}", 1)[0]
        self.assertIn("width: 40px;", ico)
        self.assertIn("height: 40px;", ico)
        self.assertIn("--page-title-gap: 24px;", css)
        main = css.split(".main {\n", 1)[1]
        self.assertIn(
            "padding: var(--page-title-gap) var(--space-4) calc(var(--page-title-gap) + var(--safe-bottom));",
            main,
        )

    def test_mobile_pg_head_gap_is_tight(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn(
            ".pg-head { margin-bottom: var(--page-title-gap); gap: var(--space-1); }",
            mobile,
        )
        self.assertNotIn(
            ".pg-head { margin-bottom: var(--page-title-gap); gap: var(--page-title-gap); }",
            mobile,
        )

    def test_all_pg_pages_tabs_above_title(self):
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
                msg=f"{path.name}: tabs must be above title",
            )


if __name__ == "__main__":
    unittest.main()
