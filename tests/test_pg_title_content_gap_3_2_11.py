"""Superseded by 3.2.14 — PG uses plain .page-head like bot."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PgTitleContentParity3211Tests(unittest.TestCase):
    def test_pg_pages_plain_page_head(self):
        pages = sorted((ROOT / "app/web/templates").glob("pg_*.html"))
        self.assertEqual(len(pages), 8)
        for path in pages:
            src = path.read_text(encoding="utf-8")
            self.assertIn('class="page-head"', src, msg=path.name)
            self.assertNotIn('class="pg-head"', src, msg=path.name)
            self.assertNotIn("pg_tabs(", src, msg=path.name)


if __name__ == "__main__":
    unittest.main()
