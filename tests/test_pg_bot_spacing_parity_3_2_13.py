"""PasarGuard title spacing mirrors bot panel (restored correct model).

Bot list pages:
  .main pad (--page-title-gap) → .page-head (title) → --page-title-gap → content

PG pages (have section tabs):
  .main pad → title FIRST (same Y as bot) → tight --space-1 → tabs
  → ONE --page-title-gap → content

Forbidden regressions:
- negative margin-top on .pg-head (clips out of .main)
- flex gap: --page-title-gap (double-stacks with margin-bottom)
- tabs ABOVE title (pushes title below bot Y / invites overflow hacks)
- changing icon/title size or .main padding-top
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"


class PgBotSpacingParityTests(unittest.TestCase):
    def test_pg_head_matches_bot_tokens_without_pull_up(self):
        css = CSS.read_text(encoding="utf-8")
        bot = css.split(".page-head {\n", 1)[1].split("}", 1)[0]
        pg = css.split(".pg-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--page-title-gap);", bot)
        self.assertIn("margin-bottom: var(--page-title-gap);", pg)
        self.assertIn("gap: var(--space-1);", pg)
        self.assertNotIn("gap: var(--page-title-gap);", pg)
        self.assertIn("margin-top: 0;", pg)
        self.assertNotIn("margin-top: calc(", pg)
        self.assertIn(".pg-head > .page-head {\n  margin-bottom: 0;\n}", css)
        main = css.split(".main {\n", 1)[1]
        self.assertIn(
            "padding: var(--page-title-gap) var(--space-4) calc(var(--page-title-gap) + var(--safe-bottom));",
            main,
        )
        ico = css.split(".page-title-ico {\n", 1)[1].split("}", 1)[0]
        self.assertIn("width: 40px;", ico)
        self.assertIn("height: 40px;", ico)

    def test_mobile_same_tokens(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        block = mobile.split(".pg-head {", 1)[1].split("}", 1)[0]
        self.assertIn("margin-top: 0;", block)
        self.assertIn("margin-bottom: var(--page-title-gap);", block)
        self.assertIn("gap: var(--space-1);", block)
        self.assertNotIn("margin-top: calc(", block)

    def test_all_pg_pages_title_before_tabs(self):
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
                head_only.find('class="page-head"'),
                head_only.find("pg_tabs("),
                msg=f"{path.name}: title must come first like bot pages",
            )


if __name__ == "__main__":
    unittest.main()
