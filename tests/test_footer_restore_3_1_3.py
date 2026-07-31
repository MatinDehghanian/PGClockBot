"""Footer restored to pre-3.0.4 / 3.0.3 shell layout (3.1.3)."""

from __future__ import annotations

import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")
BASE = Path("app/web/templates/base.html")


class FooterRestore303Tests(unittest.TestCase):
    def test_no_main_shell_wrapper(self):
        html = BASE.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        self.assertNotIn("main-shell", html)
        self.assertNotIn(".main-shell", css)
        main = html.split('<main class="main">', 1)[1].split("</main>", 1)[0]
        self.assertIn('class="main-body"', main)
        self.assertIn('class="site-footer"', main)
        self.assertGreater(main.find("site-footer"), main.find("main-body"))

    def test_no_chrome_pad_experiment_tokens(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertNotIn("--chrome-pad", css)
        self.assertNotIn("--main-pad-", css)
        self.assertNotIn("html:has(.shell)", css)
        self.assertIn(
            "padding: var(--page-title-gap) 32px calc(var(--space-3) + var(--safe-bottom));",
            css,
        )
        self.assertIn(
            "padding: var(--page-title-gap) var(--space-2) calc(var(--space-3) + var(--safe-bottom));",
            css,
        )

    def test_side_scrolls_as_a_column(self):
        css = CSS.read_text(encoding="utf-8")
        side = css.split(".side {\n", 1)[1].split(".main {", 1)[0]
        self.assertIn("overflow-y: auto;", side)
        self.assertIn(
            "padding: calc(var(--space-3) + var(--safe-top)) var(--space-2) calc(var(--space-3) + var(--safe-bottom));",
            side,
        )
        self.assertNotIn("padding-bottom: var(--chrome-pad-bottom)", css)

    def test_site_footer_classic_sticky(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".site-footer {\n  margin-top: auto;\n  padding-top: var(--space-2);", css)
        foot = css.split(".site-footer {\n", 1)[1].split("}", 1)[0]
        self.assertNotIn("position: fixed", foot)
        self.assertNotIn("position: sticky", foot)


if __name__ == "__main__":
    unittest.main()
