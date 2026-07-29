"""Release notes / changelog for the update page."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock


class ReleaseNotesTests(unittest.TestCase):
    def test_current_version_has_notes_or_fallback(self):
        from app.services.release_notes import changelog_for_update_page
        from app.version import __version__

        cl = changelog_for_update_page(local=__version__, remote=__version__)
        self.assertTrue(cl["has_notes"])
        self.assertTrue(cl["blocks"])
        self.assertTrue(cl["title"])

    def test_upgrade_path_lists_newer_versions(self):
        from app.services.release_notes import changelog_for_update_page

        cl = changelog_for_update_page(local="1.7.43", remote="1.7.45")
        self.assertTrue(cl["has_notes"])
        vers = [b["version"] for b in cl["blocks"]]
        self.assertIn("1.7.45", vers)
        self.assertIn("1.7.44", vers)
        self.assertNotIn("1.7.43", vers)

    def test_unknown_local_falls_back_to_recent(self):
        from app.services.release_notes import changelog_for_update_page

        cl = changelog_for_update_page(local="9.9.9", remote=None)
        self.assertTrue(cl["has_notes"])
        self.assertGreaterEqual(len(cl["blocks"]), 1)

    def test_update_template_renders_changelog(self):
        src = Path("app/web/templates/_settings_update.html").read_text(encoding="utf-8")
        self.assertIn("update-changelog", src)
        self.assertIn("has_notes", src)

    def test_home_no_manual_refresh(self):
        src = Path("app/web/templates/home.html").read_text(encoding="utf-8")
        self.assertNotIn(">بروزرسانی</a>", src)

    def test_sidebar_web_panel_label(self):
        src = Path("app/web/templates/base.html").read_text(encoding="utf-8")
        self.assertIn("وب پنل", src)
        self.assertIn("nav-label-home", src)


if __name__ == "__main__":
    unittest.main()
