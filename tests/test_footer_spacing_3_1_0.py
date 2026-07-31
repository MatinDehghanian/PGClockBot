"""Pinned footers + uniform section spacing (3.1.0 / refined in 3.1.1)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")


class PinnedFooterTests(unittest.TestCase):
    def test_shared_chrome_bottom_token(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("--chrome-pad-bottom:", css)
        self.assertIn("--section-gap: 16px;", css)

    def test_side_nav_scrolls_inside_column(self):
        css = CSS.read_text(encoding="utf-8")
        side = re.search(r"(?ms)^\.side\s*\{([^}]+)\}", css)
        nav = re.search(r"(?ms)^\.side-nav\s*\{([^}]+)\}", css)
        self.assertIsNotNone(side)
        self.assertIsNotNone(nav)
        self.assertIn("overflow: hidden;", side.group(1))
        self.assertIn("overflow-y: auto;", nav.group(1))

    def test_main_uses_end_of_page_shell(self):
        css = CSS.read_text(encoding="utf-8")
        main = re.search(r"(?ms)^\.main\s*\{([^}]+)\}", css)
        shell = re.search(r"(?ms)^\.main-shell\s*\{([^}]+)\}", css)
        self.assertIsNotNone(main)
        self.assertIsNotNone(shell)
        self.assertIn("overflow-y: auto;", main.group(1))
        self.assertIn("min-height: 100%;", shell.group(1))

    def test_both_footers_share_top_rule(self):
        css = CSS.read_text(encoding="utf-8")
        site = re.search(r"(?ms)^\.site-footer\s*\{([^}]+)\}", css)
        side = re.search(r"(?ms)^\.side-foot\s*\{([^}]+)\}", css)
        self.assertIsNotNone(site)
        self.assertIsNotNone(side)
        self.assertIn("padding-top: 12px;", site.group(1))
        self.assertIn("padding-top: 12px;", side.group(1))
        self.assertIn("margin-top: auto;", site.group(1))
        self.assertIn("margin-top: auto;", side.group(1))

    def test_mobile_shell_stays_viewport_locked(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        shell = re.search(r"(?ms)\.shell\s*\{([^}]+)\}", mobile)
        self.assertIsNotNone(shell)
        self.assertIn("overflow: hidden;", shell.group(1))
        self.assertIn("height: 100dvh;", shell.group(1))


class SectionGapTests(unittest.TestCase):
    def test_page_head_uses_section_gap(self):
        css = CSS.read_text(encoding="utf-8")
        head = re.search(r"(?ms)^\.page-head\s*\{([^}]+)\}", css)
        self.assertIsNotNone(head)
        self.assertIn("margin-bottom: var(--section-gap);", head.group(1))
        self.assertIn(".page-head:has(+ .section-tabs)", css)

    def test_major_blocks_use_section_gap(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".card {\n  padding: var(--card-pad);\n  margin-bottom: var(--section-gap);", css)
        self.assertIn(".home-panels {\n  display: grid;\n  grid-template-columns: 1fr;\n  gap: var(--section-gap);\n  margin-bottom: var(--section-gap);", css)
        self.assertNotIn(".card + .card {\n  margin-top: 4px;", css)

    def test_pg_home_has_tabs_after_title(self):
        src = Path("app/web/templates/pg_home.html").read_text(encoding="utf-8")
        body = src.split("{% block content %}", 1)[1]
        title_i = body.find("page_title(")
        tabs_i = body.find("pg_tabs(")
        stats_i = body.find("stats-grid")
        self.assertGreater(tabs_i, title_i)
        self.assertGreater(stats_i, tabs_i)


if __name__ == "__main__":
    unittest.main()
