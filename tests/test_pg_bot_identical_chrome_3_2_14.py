"""3.2.14 — PG pages use the same title chrome as bot (no duplicate tabs).

Root cause of years of PG title-gap bugs: horizontal pg_tabs sat between
the page title and content, while the sidebar already navigates every PG
section (same pattern as bot pages). Removing that duplicate nav makes
title→content spacing identical to bot via plain .page-head.
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
TEMPLATES = ROOT / "app/web/templates"


class PgBotIdenticalTitleChromeTests(unittest.TestCase):
    def test_pg_pages_use_plain_page_head_like_bot(self):
        pages = sorted(TEMPLATES.glob("pg_*.html"))
        self.assertEqual(len(pages), 8)
        for path in pages:
            src = path.read_text(encoding="utf-8")
            self.assertIn('class="page-head"', src, msg=path.name)
            self.assertNotIn('class="pg-head"', src, msg=path.name)
            self.assertNotIn("pg_tabs(", src, msg=path.name)

    def test_bot_and_pg_share_page_head_margin_token(self):
        css = CSS.read_text(encoding="utf-8")
        head = css.split(".page-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--page-title-gap);", head)
        self.assertIn("--page-title-gap: 24px;", css)
        self.assertNotIn(
            "margin-top: calc(-1 * (var(--btn-h) + var(--space-1)));",
            css,
        )

    def test_sidebar_still_has_pg_nav(self):
        base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
        self.assertIn("nav-section-pg", base)
        self.assertIn('href="/pg"', base)
        self.assertIn('href="/pg/users"', base)
        self.assertIn('href="/pg/nodes"', base)

    def test_users_bot_page_has_no_section_tabs(self):
        src = (TEMPLATES / "users.html").read_text(encoding="utf-8")
        self.assertIn('class="page-head"', src)
        self.assertNotIn("section-tabs", src)


if __name__ == "__main__":
    unittest.main()
