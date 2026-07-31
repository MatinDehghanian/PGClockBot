"""Equal page-title gaps + single font family (3.1.8).

Above title (.main padding-top) == below title (.page-head margin-bottom).
Bot and PasarGuard use the same --page-title-gap token.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")
BASE = Path("app/web/templates/base.html")


class PageTitleGapParityTests(unittest.TestCase):
    def test_page_title_gap_token(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("--page-title-gap: 16px;", css)

    def test_main_top_matches_page_head_bottom(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(
            "padding: var(--page-title-gap) 32px calc(var(--space-3) + var(--safe-bottom));",
            css,
        )
        self.assertIn(".page-head {\n  display: flex;", css)
        head = css.split(".page-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--page-title-gap);", head)
        # no asymmetric title→tabs shrink
        self.assertNotIn(".page-head:has(+ .section-tabs)", css)
        self.assertNotIn(".page-head:has(+ .settings-tabs)", css)

    def test_pg_title_gap_identical_to_bot(self):
        css = CSS.read_text(encoding="utf-8")
        # .pg-head owns the same gap token as bot .page-head; nested title has no extra mb
        pg = css.split(".pg-head {\n", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--page-title-gap);", pg)
        self.assertIn(".pg-head > .page-head {\n  margin-bottom: 0;\n}", css)
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn(
            "padding: var(--page-title-gap) var(--space-2) calc(var(--space-3) + var(--safe-bottom));",
            mobile,
        )
        self.assertIn(".page-head { margin-bottom: var(--page-title-gap);", mobile)
        self.assertIn(".pg-head { margin-bottom: var(--page-title-gap);", mobile)
        self.assertIn(".pg-head > .page-head { margin-bottom: 0; }", mobile)

    def test_pg_tabs_sit_above_title(self):
        """Tabs above title — otherwise they inflate title→content vs bot."""
        pages = sorted(Path("app/web/templates").glob("pg_*.html"))
        self.assertTrue(pages)
        for path in pages:
            src = path.read_text(encoding="utf-8")
            head = src.split('class="pg-head"', 1)[1]
            head_only = re.split(
                r'<div class="card|<div class="stats-grid|<div class="flash|<div class="pg-admin-head|{%\s*if\s+not\s+is_admin',
                head,
                maxsplit=1,
            )[0]
            tabs_at = head_only.find("pg_tabs(")
            title_at = head_only.find('class="page-head"')
            self.assertGreaterEqual(tabs_at, 0, msg=path.name)
            self.assertGreaterEqual(title_at, 0, msg=path.name)
            self.assertLess(tabs_at, title_at, msg=f"{path.name}: tabs must be above title")


class PanelFontUnityTests(unittest.TestCase):
    def test_single_font_family_token(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn('--font: "Vazirmatn", sans-serif;', css)
        self.assertNotIn("--mono:", css)
        self.assertNotIn("Cascadia", css)
        self.assertNotIn("Consolas", css)
        self.assertNotIn("Tahoma", css)
        self.assertNotIn("ui-monospace", css)
        self.assertNotIn("ui-sans-serif", css)
        self.assertNotIn("system-ui", css)
        # mono utility keeps numerals tabular but same family
        self.assertIn(".mono { font-family: var(--font);", css)
        self.assertIn('font-family: var(--font);', css)
        # no leftover mono variable references
        self.assertNotIn("var(--mono)", css)

    def test_base_loads_vazirmatn_only(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertIn("family=Vazirmatn", html)
        self.assertEqual(html.count("fonts.googleapis.com/css2"), 1)


if __name__ == "__main__":
    unittest.main()
