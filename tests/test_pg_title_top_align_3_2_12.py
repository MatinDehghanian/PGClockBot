"""3.2.12 — superseded by 3.2.13: no negative pull-up (it clipped out of .main)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"


class PgTitleTopAlign3212Tests(unittest.TestCase):
    def test_no_negative_pull_up(self):
        css = CSS.read_text(encoding="utf-8")
        pg = css.split(".pg-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-top: 0;", pg)
        self.assertNotIn("margin-top: calc(", pg)
        self.assertIn("margin-bottom: var(--page-title-gap);", pg)
        self.assertIn("gap: var(--space-1);", pg)

    def test_mobile_no_negative_pull_up(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        block = mobile.split(".pg-head {", 1)[1].split("}", 1)[0]
        self.assertIn("margin-top: 0;", block)
        self.assertNotIn("margin-top: calc(", block)

    def test_title_before_tabs(self):
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
                msg=path.name,
            )


if __name__ == "__main__":
    unittest.main()
