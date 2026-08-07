"""3.2.18 — status select opens upward; ticket upload matches panel upload-box."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_version_at_least_3_2_18(self):
        from app.services.release_notes import RELEASE_NOTES_FA
        from app.version import __version__

        self.assertGreaterEqual(tuple(int(x) for x in __version__.split(".")), (3, 2, 18))
        self.assertIn("3.2.18", RELEASE_NOTES_FA)


class UiSelectDropUpTests(unittest.TestCase):
    def test_js_ticket_status_up_others_auto(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("function placeUiSelectMenu", js)
        self.assertIn("drop-up", js)
        place = js[js.find("function placeUiSelectMenu") : js.find("function enhanceSelect")]
        # Only ticket status forced up — not every modal select
        self.assertIn("ticket-status-form, .ticket-status-actions", place)
        self.assertNotIn(".ui-modal", place)
        # Auto: prefer down when space allows
        self.assertIn("roomBelow >= mh", place)
        self.assertLess(place.find("ticket-status-form"), place.find("roomBelow >= mh"))

    def test_css_drop_up(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".ui-select.drop-up .ui-select-menu:not(.is-fixed-pos):not(.is-ported)", css)
        self.assertIn("bottom: calc(100% + var(--space-1))", css)


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
