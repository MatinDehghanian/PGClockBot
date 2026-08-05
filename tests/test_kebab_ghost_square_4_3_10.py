"""v4.3.10 — kebab overlay must not paint a ghost square inside table cells."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")


class KebabGhostSquareTests(unittest.TestCase):
    def test_no_in_cell_open_display_flex(self):
        """Opening kebab must not unhide the menu while it still lives in the <td>."""
        self.assertNotIn(".row-actions.open .row-actions-menu { display: flex; }", CSS)
        self.assertNotIn(
            ".table-wrap.force-kebab .row-actions.open .row-actions-menu { display: flex; }",
            CSS,
        )

    def test_in_cell_menu_forced_hidden(self):
        mobile = CSS.split("@media (max-width: 1100px)")[2].split("/* Any viewport:")[0]
        self.assertIn(".row-actions-menu {", mobile)
        block = mobile.split(".row-actions-menu {")[1].split("}")[0]
        self.assertIn("display: none !important", block)

        force = CSS.split(".table-wrap.force-kebab .row-actions-menu {")[1].split("}")[0]
        self.assertIn("display: none !important", force)

    def test_only_ported_menu_visible(self):
        ported = re.search(r"(?ms)^\.row-actions-menu\.is-ported\s*\{([^}]+)\}", CSS)
        self.assertIsNotNone(ported)
        self.assertIn("display: flex !important", ported.group(1))

    def test_place_hides_until_positioned(self):
        place = JS.split("function placeRowMenu")[1].split("function restoreUiSelectMenu")[0]
        if "function clearUiSelectMenuPos" in place:
            place = place.split("function clearUiSelectMenuPos")[0]
        # Split before custom selects block
        place = place.split("/* Custom selects")[0]
        self.assertIn("visibility = 'hidden'", place)
        self.assertIn("document.body.appendChild(menu)", place)
        self.assertIn("is-ported", place)
        # Final reveal after top/left assigned
        self.assertIn("visibility = ''", place)
        self.assertLess(place.index("visibility = 'hidden'"), place.index("visibility = ''"))

    def test_restore_clears_visibility(self):
        restore = JS.split("function restoreRowMenu")[1].split("function closeRowActions")[0]
        self.assertIn("visibility", restore)

    def test_light_theme_no_inline_menu_card_paint(self):
        """Light theme must not paint a card box behind inline (non-overlay) actions."""
        self.assertNotRegex(
            CSS,
            r"html\[data-theme=\"light\"\][^{]*\.row-actions-menu\s*,",
        )
        self.assertIn(
            'html[data-theme="light"] .row-actions-menu.is-ported',
            CSS,
        )


class VersionTests(unittest.TestCase):
    def test_version(self):
        from app.version import __version__

        self.assertEqual(__version__, "4.3.10")
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "4.3.10")


if __name__ == "__main__":
    unittest.main()
