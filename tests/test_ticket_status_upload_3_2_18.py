"""3.2.18 — status select opens upward; ticket upload matches panel upload-box."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_version(self):
        from app.version import __version__

        self.assertEqual(__version__, "3.2.18")
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "3.2.18")


class UiSelectDropUpTests(unittest.TestCase):
    def test_js_prefers_up_in_modal(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("function placeUiSelectMenu", js)
        self.assertIn("ticket-status-form", js)
        self.assertIn("drop-up", js)
        self.assertIn("placeUiSelectMenu(wrap)", js)

    def test_css_drop_up(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".ui-select.drop-up .ui-select-menu", css)
        self.assertIn("bottom: calc(100%", css)


class UploadBoxTests(unittest.TestCase):
    def test_tickets_use_upload_box(self):
        src = (ROOT / "app/web/templates/tickets.html").read_text(encoding="utf-8")
        self.assertIn('class="file-label upload-box"', src)
        self.assertIn("upload-box-plus", src)
        self.assertIn("data-upload-name", src)
        self.assertGreaterEqual(src.count('name="attachment"'), 2)
        # Raw unstyled file input labels removed
        self.assertNotIn("<label class=\"form-field\">پیوست", src)


if __name__ == "__main__":
    unittest.main()
