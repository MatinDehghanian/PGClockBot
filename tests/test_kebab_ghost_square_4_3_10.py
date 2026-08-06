"""Kebab overlay must not paint a ghost square inside table cells.

Regression: in-cell .row-actions-menu with background/border/fixed paints over
adjacent columns (e.g. volume) even when the real menu is body-ported.
"""

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

    def test_in_cell_menu_is_inert_no_chrome(self):
        """In-cell kebab shell must be display:none and have zero visual chrome."""
        self.assertIn(".row-actions-menu:not(.is-ported)", CSS)
        # Prefer the force-kebab block (always present); also require mobile media copy
        force = CSS.split(
            ".table-wrap.force-kebab .row-actions-menu:not(.is-ported) {"
        )[1].split("}")[0]
        self.assertIn("display: none !important", force)
        self.assertIn("background: transparent !important", force)
        self.assertIn("box-shadow: none !important", force)
        self.assertIn("padding: 0 !important", force)
        self.assertIn("min-width: 0 !important", force)
        self.assertNotIn("background: var(--bg-elevated", force)
        # Mobile media must also inert the in-cell menu
        self.assertGreaterEqual(CSS.count(".row-actions-menu:not(.is-ported) {"), 2)

    def test_only_ported_menu_has_chrome(self):
        ported = re.search(r"(?ms)^\.row-actions-menu\.is-ported\s*\{([^}]+)\}", CSS)
        self.assertIsNotNone(ported)
        body = ported.group(1)
        self.assertIn("display: flex !important", body)
        self.assertIn("position: fixed !important", body)
        self.assertIn("background: var(--bg-elevated, var(--bg-card));", body)
        self.assertIn("box-shadow:", body)
        self.assertIn("padding: var(--space-1);", body)

    def test_col_actions_not_clipped(self):
        self.assertIn("td:not(.col-actions)", CSS)
        self.assertIn("td.col-actions", CSS)
        col = CSS.split("td.col-actions {")[1].split("}")[0]
        self.assertIn("overflow: visible;", col)

    def test_card_overflow_visible_not_clip(self):
        """overflow clip/hidden on .card traps fixed menus → ghost squares."""
        block = CSS.split("\n.card {")[1].split("}")[0]
        self.assertIn("overflow: visible;", block)
        self.assertNotIn("overflow-x: clip", block)

    def test_place_hides_until_positioned(self):
        place = JS.split("function placeRowMenu")[1].split("function restoreUiSelectMenu")[0]
        if "function clearUiSelectMenuPos" in place:
            place = place.split("function clearUiSelectMenuPos")[0]
        place = place.split("/* Custom selects")[0]
        self.assertIn("visibility = 'hidden'", place)
        self.assertIn("document.body.appendChild(menu)", place)
        self.assertIn("classList.add('is-ported')", place)
        self.assertIn("menu.hidden = true", place)
        self.assertIn("menu.hidden = false", place)
        self.assertIn("visibility = ''", place)
        self.assertLess(place.index("visibility = 'hidden'"), place.index("visibility = ''"))
        self.assertLess(
            place.index("appendChild(menu)"),
            place.index("classList.add('is-ported')"),
        )

    def test_restore_clears_ported_and_hidden(self):
        restore = JS.split("function restoreRowMenu")[1].split("function closeRowActions")[0]
        self.assertIn("is-ported", restore)
        self.assertIn("menu.hidden = false", restore)
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
        self.assertNotIn(
            'html[data-theme="light"] .table-wrap.force-kebab .row-actions-menu',
            CSS,
        )


class VersionTests(unittest.TestCase):
    def test_version_at_least_4_4_10(self):
        from app.version import __version__

        self.assertGreaterEqual(
            tuple(int(x) for x in __version__.split(".")), (4, 4, 10)
        )
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertGreaterEqual(tuple(int(x) for x in ver.split(".")), (4, 4, 10))


if __name__ == "__main__":
    unittest.main()
