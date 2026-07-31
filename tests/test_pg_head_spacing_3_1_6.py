"""PasarGuard header chrome (3.1.6) — actions stay on title row; tabs marked."""

from __future__ import annotations

import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")
MACRO = Path("app/web/templates/macros.html")


class PgHeadSpacingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
