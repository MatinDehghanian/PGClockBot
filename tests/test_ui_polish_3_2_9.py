"""UI polish 3.2.9 — thead clip, theme separator air, force-join add tiles."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
JS = ROOT / "app/web/static/panel.js"
SETTINGS_FIELD = ROOT / "app/web/templates/_settings_field.html"


class TheadClipTests(unittest.TestCase):
    def test_flush_card_clips_and_table_wrap_owns_radius(self):
        css = CSS.read_text(encoding="utf-8")
        flush = css.split(".card.card-flush {\n", 1)[1].split("}", 1)[0]
        self.assertIn("overflow: hidden;", flush)
        wrap = css.split(".card.card-flush > .table-wrap {\n", 1)[1].split("}", 1)[0]
        self.assertIn("overflow: auto;", wrap)
        self.assertIn(
            ".card.card-flush > .table-wrap:first-child {\n"
            "  border-start-start-radius: var(--radius);\n"
            "  border-start-end-radius: var(--radius);\n"
            "}",
            css,
        )
        self.assertIn(
            ".card.card-flush > .table-wrap:first-child > table > thead > tr > th:first-child {\n"
            "  border-start-start-radius: var(--radius);\n"
            "}",
            css,
        )
        self.assertIn("border-collapse: separate;", css)
        self.assertIn("border-spacing: 0;", css)


class ThemeSeparatorAirTests(unittest.TestCase):
    def test_theme_air_matches_brand_gap(self):
        css = CSS.read_text(encoding="utf-8")
        theme = css.split(".side-theme {\n", 1)[1].split("}", 1)[0]
        self.assertIn("padding: 0 0 var(--space-2);", theme)
        self.assertIn("margin-bottom: var(--space-1);", theme)
        first = css.split(".side-nav > .nav-section:first-child", 1)[1].split("}", 1)[0]
        self.assertIn("margin-top: 0;", first)


class ForceJoinCardGridTests(unittest.TestCase):
    def test_channel_cards_and_dashed_add_tile(self):
        html = SETTINGS_FIELD.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        self.assertNotIn("force-channels-footer", html)
        self.assertIn("force-channels-list", html)
        self.assertIn("grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));", css)
        self.assertIn(".force-channel-add {", css)
        self.assertIn("border: 1px dashed", css)
        self.assertIn("addTileHtml", js)
        self.assertIn("data-force-channels-add", js)
        self.assertIn("force-channel-add-plus", js)
        self.assertIn("force-channel-foot", js)
        list_mobile = css.split("@media (max-width: 720px)", 1)[1]
        self.assertIn(".force-channels-list {\n    grid-template-columns: 1fr;", list_mobile)


if __name__ == "__main__":
    unittest.main()
