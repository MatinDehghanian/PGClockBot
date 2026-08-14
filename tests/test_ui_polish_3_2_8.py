"""UI polish 3.2.8 — theme menu width, force-join compact row, nav item gap."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
JS = ROOT / "app/web/static/panel.js"


class ThemeMenuWidthTests(unittest.TestCase):
    def test_theme_menu_matches_nav_box_width(self):
        css = CSS.read_text(encoding="utf-8")
        theme = css.split(".side-theme {\n", 1)[1].split("}", 1)[0]
        self.assertIn("padding: 0 0 var(--space-2);", theme)
        menu = css.split(".side-theme-menu {\n", 1)[1].split("}", 1)[0]
        self.assertIn("inset-inline: 0;", menu)
        self.assertNotIn("inset-inline: var(--space-1);", menu)


class NavItemGapTests(unittest.TestCase):
    def test_nav_items_have_small_gap(self):
        css = CSS.read_text(encoding="utf-8")
        section = css.split(".nav-section {\n", 1)[1].split("}", 1)[0]
        self.assertIn("gap: var(--space-0);", section)
        colored = css.split(".nav-section-bot,\n.nav-section-pg,\n.nav-section-home {\n", 1)[1].split("}", 1)[0]
        self.assertIn("gap: var(--space-0);", colored)


class ForceJoinCompactTests(unittest.TestCase):
    def test_narrow_field_with_controls_beside(self):
        css = CSS.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        row = css.split(".force-channel-row {\n", 1)[1].split("}", 1)[0]
        self.assertIn("display: flex;", row)
        self.assertIn("flex-direction: column;", row)
        wrap = css.split(".force-channel-id-wrap {\n", 1)[1].split("}", 1)[0]
        # Later switched from a fixed width to a flex-grow shorthand so the
        # field still fills the row beside its controls inside the flex
        # container — same "narrow field, controls beside" layout intent.
        self.assertIn("flex: 1 1 auto;", wrap)
        self.assertIn("btn-danger", js)
        self.assertIn("force-channel-remove", js)
        self.assertIn("force-channel-add", js)
        self.assertIn("addTileHtml", js)


if __name__ == "__main__":
    unittest.main()
