"""Upload progress remains; welcome/middle photo fully removed (2.8.2)."""

from __future__ import annotations

import unittest
from pathlib import Path


class WelcomePhotoRemovedTests(unittest.TestCase):
    def test_no_welcome_image_anywhere(self):
        from app.services.users import DEFAULT_SETTINGS, IMAGE_KEYS

        self.assertNotIn("welcome_image", DEFAULT_SETTINGS)
        self.assertNotIn("welcome_image", IMAGE_KEYS)
        ap = Path("app/web/templates/_settings_appearance.html").read_text(encoding="utf-8")
        self.assertNotIn("welcome_image", ap)
        self.assertNotIn("عکس پیام وسط", ap)
        start = Path("app/bot/handlers/start.py").read_text(encoding="utf-8")
        self.assertNotIn("welcome_image", start)
        self.assertNotIn("answer_photo", start)
        self.assertIn("edit_text", start)
        appearance = Path("app/services/bot_appearance.py").read_text(encoding="utf-8")
        # Cleared on save (bulk), but no upload field
        self.assertIn('"welcome_image": ""', appearance)

    def test_edit_recovers_legacy_photo_menu(self):
        src = Path("app/bot/handlers/start.py").read_text(encoding="utf-8")
        self.assertIn("Legacy photo home messages", src)
        self.assertIn('getattr(message, "photo", None)', src)


class UploadProgressTests(unittest.TestCase):
    def test_progress_markup_and_js(self):
        js = Path("app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("initUploadProgress", js)
        self.assertIn("آپلود با موفقیت انجام شد", js)
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".upload-box-progress", css)


if __name__ == "__main__":
    unittest.main()
