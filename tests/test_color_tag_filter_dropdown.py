"""Resellers/users risk-tag filter is a dropdown under the list title — not pills."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ColorTagFilterDropdownTests(unittest.TestCase):
    def test_resellers_uses_dropdown_under_title(self):
        src = (ROOT / "app/web/templates/resellers.html").read_text(encoding="utf-8")
        list_block = src.split("<h2>لیست نمایندگان</h2>", 1)[1].split(
            'class="search-bar"', 1
        )[0]
        self.assertIn("color-tag-toolbar", list_block)
        self.assertIn("data-color-tag-nav", list_block)
        self.assertIn("color-tag-select", list_block)
        self.assertNotIn("color-tag-filters", list_block)
        self.assertNotIn("color-tag-filter", list_block)

    def test_users_uses_dropdown_not_pills(self):
        src = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
        self.assertIn("color-tag-toolbar", src)
        self.assertIn("data-color-tag-nav", src)
        self.assertNotIn("color-tag-filters", src)

    def test_css_toolbar_shares_card_pad(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        block = css.split(".card.card-flush > .color-tag-toolbar", 1)[1].split(
            ".color-tag-select-wrap", 1
        )[0]
        self.assertIn("var(--card-pad)", block)

    def test_js_navigates_on_change(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("data-color-tag-nav", js)
        self.assertIn("window.location.assign", js)


if __name__ == "__main__":
    unittest.main()
