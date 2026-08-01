"""Superseded by 3.2.14 — PG chrome identical to bot via plain .page-head."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"


class PgBotSpacingParityTests(unittest.TestCase):
    def test_page_head_token(self):
        css = CSS.read_text(encoding="utf-8")
        head = css.split(".page-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--page-title-gap);", head)

    def test_pg_pages_no_duplicate_tabs(self):
        pages = sorted((ROOT / "app/web/templates").glob("pg_*.html"))
        self.assertEqual(len(pages), 8)
        for path in pages:
            src = path.read_text(encoding="utf-8")
            self.assertNotIn("pg_tabs(", src, msg=path.name)
            self.assertNotIn('class="pg-head"', src, msg=path.name)


if __name__ == "__main__":
    unittest.main()
