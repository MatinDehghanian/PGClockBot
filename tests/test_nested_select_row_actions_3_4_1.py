"""3.4.1 — nested ui-select must not dismiss row-actions kebab."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")


class NestedSelectRowActionsTests(unittest.TestCase):
    def test_select_toggle_skips_close_row_actions_when_nested(self):
        # Extract the ui-select toggle click handler body
        m = re.search(
            r"toggle\.addEventListener\('click',\s*\(ev\)\s*=>\s*\{(.*?)\n\s*\}\);",
            JS,
            re.S,
        )
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("nestedInRowMenu", body)
        self.assertIn(".row-actions-menu", body)
        self.assertIn("if (!nestedInRowMenu)", body)
        self.assertIn("closeRowActions()", body)
        # Must NOT unconditionally close row actions before the nested guard
        before_guard = body.split("nestedInRowMenu")[0]
        self.assertNotIn("closeRowActions()", before_guard)

    def test_outside_click_treats_ui_select_menu_as_inside_row_menu(self):
        self.assertIn("e.target.closest('.ui-select-menu')", JS)
        self.assertIn("inRowMenu", JS)

    def test_scroll_ignores_nested_select_menu(self):
        scroll_block = JS.split("window.addEventListener('scroll', (e) => {")[2].split(
            "}, true);"
        )[0]
        self.assertIn(".ui-select-menu", scroll_block)
        self.assertIn(".row-actions-menu", scroll_block)

    def test_nested_open_select_z_index(self):
        self.assertIn(".row-actions-menu .ui-select.open", CSS)
        self.assertIn("z-index: 5", CSS.split(".row-actions-menu .ui-select.open")[1].split("}")[0])

    def test_users_and_resellers_role_select_in_row_actions(self):
        users = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
        resellers = (ROOT / "app/web/templates/resellers.html").read_text(encoding="utf-8")
        self.assertIn("row-actions-stack", users)
        self.assertIn('name="role"', users)
        self.assertIn("row-actions-stack", resellers)
        self.assertIn('name="role"', resellers)


class VersionBumpTests(unittest.TestCase):
    def test_version_at_least_3_4_1(self):
        from app.version import __version__

        self.assertGreaterEqual(tuple(int(x) for x in __version__.split(".")), (3, 4, 1))
        notes = (ROOT / "app/services/release_notes.py").read_text(encoding="utf-8")
        self.assertIn('"3.4.1"', notes)


if __name__ == "__main__":
    unittest.main()
