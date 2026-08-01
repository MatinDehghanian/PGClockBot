"""PasarGuard header chrome — actions stay on title row (updated 3.2.14)."""

from __future__ import annotations

import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")
MACRO = Path("app/web/templates/macros.html")


class PgHeadSpacingTests(unittest.TestCase):
    def test_page_head_actions_do_not_drop_below_title(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".page-head > .actions,\n.page-head > .btn {\n  margin-top: 0;", css)

    def test_pg_tabs_macro_still_defined_but_unused_on_pages(self):
        # Macro kept for compatibility; pages no longer inject duplicate horizontal tabs
        src = MACRO.read_text(encoding="utf-8")
        self.assertIn('class="section-tabs pg-tabs"', src)
        pages = sorted(Path("app/web/templates").glob("pg_*.html"))
        self.assertTrue(pages)
        for path in pages:
            page = path.read_text(encoding="utf-8")
            self.assertNotIn("pg_tabs(", page, msg=path.name)
            self.assertNotIn('class="pg-head"', page, msg=path.name)
            self.assertIn('class="page-head"', page, msg=path.name)


if __name__ == "__main__":
    unittest.main()
