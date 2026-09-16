"""Color tag + atmospheric title polish contracts."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ColorTagContractTests(unittest.TestCase):
    def test_model_has_color_tag(self):
        models = (ROOT / "app/db/models.py").read_text(encoding="utf-8")
        self.assertIn("color_tag", models)
        mig = (ROOT / "alembic/versions/0027_bot_users_color_tag.py").read_text(encoding="utf-8")
        self.assertIn("color_tag", mig)
        self.assertIn("0026_reseller_bot_token_hash", mig)

    def test_staff_note_accepts_color_tag(self):
        src = (ROOT / "app/api/ux20_pages.py").read_text(encoding="utf-8")
        note = src.split("async def users_staff_note")[1].split("async def ")[0]
        self.assertIn("color_tag", note)
        self.assertIn('"blue", "red", "green", "yellow"', note)

    def test_templates_colorize_names(self):
        users = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
        resellers = (ROOT / "app/web/templates/resellers.html").read_text(encoding="utf-8")
        edit = (ROOT / "app/web/templates/_user_edit_body.html").read_text(encoding="utf-8")
        self.assertIn("color-tag-", users)
        self.assertIn("color-tag-", resellers)
        self.assertIn("color_tag_picker", edit)


class AtmosphereTitleContractTests(unittest.TestCase):
    def test_page_title_has_watermark_mark(self):
        macros = (ROOT / "app/web/templates/macros.html").read_text(encoding="utf-8")
        self.assertIn("page-title-mark", macros)
        self.assertIn("page-title-watermark", macros)
        self.assertIn("page_svg", macros)
        self.assertIn("modal_title", macros)

    def test_base_has_panel_atmosphere_and_tone(self):
        base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
        self.assertIn('data-panel-tone=', base)
        self.assertIn("panel-atmosphere", base)
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".panel-atmosphere", css)
        self.assertIn("page-title-watermark", css)
        # Status/404 page language left intact
        self.assertIn(".panel-status-watermark", css)
        self.assertIn(".panel-status-badge", css)


if __name__ == "__main__":
    unittest.main()
