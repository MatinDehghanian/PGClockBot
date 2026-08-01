"""Superseded by 3.2.14 — no pull-up; no pg-head tabs stack."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"


class PgTitleTopAlign3212Tests(unittest.TestCase):
    def test_no_negative_pull_up(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertNotIn(
            "margin-top: calc(-1 * (var(--btn-h) + var(--space-1)));",
            css,
        )

    def test_pg_pages_plain_page_head(self):
        pages = sorted((ROOT / "app/web/templates").glob("pg_*.html"))
        for path in pages:
            src = path.read_text(encoding="utf-8")
            self.assertNotIn('class="pg-head"', src, msg=path.name)
            self.assertNotIn("pg_tabs(", src, msg=path.name)


if __name__ == "__main__":
    unittest.main()
