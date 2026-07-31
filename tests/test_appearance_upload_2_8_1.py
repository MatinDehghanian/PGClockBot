"""Appearance welcome photo + upload progress (2.8.1)."""

from __future__ import annotations

import unittest
from pathlib import Path


class AppearanceWelcomePhotoTests(unittest.TestCase):
    def test_under_middle_text_not_welcome_tab(self):
        ap = Path("app/web/templates/_settings_appearance.html").read_text(encoding="utf-8")
        self.assertIn('name="welcome_image"', ap)
        self.assertIn("متن وسط صفحه", ap)
        # Middle text comes before welcome image field
        mid = ap.index("bot_tg_description")
        img = ap.index('name="welcome_image"')
        self.assertLess(mid, img)
        field = Path("app/web/templates/_settings_field.html").read_text(encoding="utf-8")
        # Generic image fields no longer the only place — welcome removed from groups
        from app.services.users import SETTING_GROUPS

        keys = [f[0] for f in SETTING_GROUPS["خوش‌آمد و هویت"]]
        self.assertNotIn("welcome_image", keys)

    def test_start_sends_photo_safely(self):
        src = Path("app/bot/handlers/start.py").read_text(encoding="utf-8")
        self.assertIn("_clip_caption", src)
        self.assertIn("relative_to(uploads_root)", src)
        self.assertIn("answer_photo", src)


class UploadProgressTests(unittest.TestCase):
    def test_progress_markup_and_js(self):
        js = Path("app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("initUploadProgress", js)
        self.assertIn("آپلود با موفقیت انجام شد", js)
        self.assertIn("xhr.upload.onprogress", js)
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".upload-box-progress", css)
        self.assertIn(".upload-box-progress-bar", css)
        ap = Path("app/web/templates/_settings_appearance.html").read_text(encoding="utf-8")
        self.assertIn("upload-box-progress", ap)


if __name__ == "__main__":
    unittest.main()
