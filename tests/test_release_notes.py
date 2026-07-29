"""Release notes / changelog for the update page."""

from __future__ import annotations

import unittest
from pathlib import Path


class ReleaseNotesTests(unittest.TestCase):
    def test_current_version_has_single_block(self):
        from app.services.release_notes import changelog_for_update_page
        from app.version import __version__

        cl = changelog_for_update_page(local=__version__, remote=__version__)
        self.assertTrue(cl["has_notes"])
        self.assertEqual(len(cl["blocks"]), 1)
        self.assertTrue(cl["title"])

    def test_upgrade_shows_only_latest_remote(self):
        from app.services.release_notes import changelog_for_update_page

        cl = changelog_for_update_page(local="1.7.43", remote="1.7.45")
        self.assertTrue(cl["has_notes"])
        self.assertEqual(len(cl["blocks"]), 1)
        self.assertEqual(cl["blocks"][0]["version"], "1.7.45")

    def test_unknown_local_falls_back_to_newest(self):
        from app.services.release_notes import changelog_for_update_page, RELEASE_NOTES_FA

        cl = changelog_for_update_page(local="9.9.9", remote=None)
        self.assertTrue(cl["has_notes"])
        self.assertEqual(len(cl["blocks"]), 1)
        newest = next(iter(RELEASE_NOTES_FA))
        self.assertEqual(cl["blocks"][0]["version"], newest)

    def test_update_template_simplified(self):
        src = Path("app/web/templates/_settings_update.html").read_text(encoding="utf-8")
        self.assertIn("update-changelog", src)
        self.assertIn("get.sh", src)
        self.assertIn("گزینه ۲", src)
        self.assertNotIn("گیت‌هاب", src)
        self.assertNotIn("upd-clear", src)
        self.assertNotIn("پاک‌سازی وضعیت", src)

    def test_home_no_manual_refresh(self):
        src = Path("app/web/templates/home.html").read_text(encoding="utf-8")
        self.assertNotIn(">بروزرسانی</a>", src)

    def test_sidebar_web_panel_label(self):
        src = Path("app/web/templates/base.html").read_text(encoding="utf-8")
        self.assertIn("وب پنل", src)
        self.assertIn("nav-label-home", src)


if __name__ == "__main__":
    unittest.main()
