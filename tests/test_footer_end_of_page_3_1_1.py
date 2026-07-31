"""End-of-page sticky footers (3.1.1) — not floating / not mid-viewport."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")
BASE = Path("app/web/templates/base.html")


class EndOfPageFooterTests(unittest.TestCase):
    def test_main_shell_wraps_body_and_footer(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertIn('class="main-shell"', html)
        # footer is inside main-shell, after main-body
        shell = html.split('class="main-shell"', 1)[1].split("</main>", 1)[0]
        self.assertIn('class="main-body"', shell)
        self.assertIn('class="site-footer"', shell)
        self.assertGreater(shell.find("site-footer"), shell.find("main-body"))

    def test_main_scrolls_as_a_whole(self):
        css = CSS.read_text(encoding="utf-8")
        main = re.search(r"(?ms)^\.main\s*\{([^}]+)\}", css)
        self.assertIsNotNone(main)
        body = main.group(1)
        self.assertIn("overflow-y: auto;", body)
        self.assertNotIn("overflow: hidden;", body)
        self.assertIn("padding: var(--main-pad-top) var(--main-pad-x) var(--chrome-pad-bottom);", body)

    def test_main_shell_sticky_footer_pattern(self):
        css = CSS.read_text(encoding="utf-8")
        shell = re.search(r"(?ms)^\.main-shell\s*\{([^}]+)\}", css)
        body = re.search(r"(?ms)^\.main-body\s*\{([^}]+)\}", css)
        foot = re.search(r"(?ms)^\.site-footer\s*\{([^}]+)\}", css)
        self.assertIsNotNone(shell)
        self.assertIsNotNone(body)
        self.assertIsNotNone(foot)
        self.assertIn("min-height: 100%;", shell.group(1))
        self.assertIn("display: flex;", shell.group(1))
        self.assertIn("flex: 1 0 auto;", body.group(1))
        self.assertNotIn("overflow-y: auto;", body.group(1))
        self.assertIn("margin-top: auto;", foot.group(1))
        self.assertNotIn("padding-bottom: var(--chrome-pad-bottom);", foot.group(1))
        self.assertNotIn("position: fixed;", foot.group(1))
        self.assertNotIn("position: sticky;", foot.group(1))

    def test_side_foot_keeps_bottom_padding_for_alignment(self):
        css = CSS.read_text(encoding="utf-8")
        side = re.search(r"(?ms)^\.side-foot\s*\{([^}]+)\}", css)
        self.assertIsNotNone(side)
        self.assertIn("padding-bottom: var(--chrome-pad-bottom);", side.group(1))
        self.assertIn("margin-top: auto;", side.group(1))

    def test_section_gap_still_standard(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("--section-gap: 16px;", css)
        self.assertIn(".page-head:has(+ .section-tabs)", css)


if __name__ == "__main__":
    unittest.main()
