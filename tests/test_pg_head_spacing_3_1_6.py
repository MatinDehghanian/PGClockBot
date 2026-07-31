"""PasarGuard header spacing matches bot panel title→content gap (3.1.6)."""

from __future__ import annotations

import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")
MACRO = Path("app/web/templates/macros.html")


class PgHeadSpacingTests(unittest.TestCase):
    def test_pg_head_unit_matches_bot_page_head_gap(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".pg-head {\n  margin-bottom: var(--space-4);", css)
        self.assertIn(".pg-head > .page-head {\n  margin-bottom: 8px;", css)
        self.assertIn(".pg-head > .pg-tabs,\n.pg-head > .section-tabs {\n  margin-bottom: 0;", css)
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn(".pg-head { margin-bottom: var(--space-3); }", mobile)

    def test_page_head_actions_do_not_drop_below_title(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".page-head > .actions,\n.page-head > .btn {\n  margin-top: 0;", css)

    def test_pg_tabs_macro_marks_nav(self):
        src = MACRO.read_text(encoding="utf-8")
        self.assertIn('class="section-tabs pg-tabs"', src)

    def test_all_pg_pages_wrap_head_and_tabs(self):
        pages = sorted(Path("app/web/templates").glob("pg_*.html"))
        self.assertTrue(pages)
        for path in pages:
            src = path.read_text(encoding="utf-8")
            self.assertIn('class="pg-head"', src, msg=path.name)
            self.assertIn("pg_tabs(", src, msg=path.name)
            # tabs render inside pg-head (after page-head, before closing pg-head)
            head = src.split('class="pg-head"', 1)[1]
            # crude: first card/stats should be outside — pg_tabs call appears before </div> that closes pg-head
            self.assertIn("pg_tabs(", head.split('<div class="card', 1)[0], msg=path.name)


if __name__ == "__main__":
    unittest.main()
