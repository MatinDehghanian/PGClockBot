"""Panel UI polish: switch thumb, select vertical center, preview chrome."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
CHAT_PREVIEW = (ROOT / "app/web/templates/_tg_preview_chat.html").read_text(encoding="utf-8")
AP_PREVIEW = (ROOT / "app/web/templates/_tg_preview_appearance.html").read_text(encoding="utf-8")


class SwitchThumbFitTests(unittest.TestCase):
    def test_on_travel_fits_inside_track(self):
        self.assertIn("--sw-travel: 16px", CSS)
        track = CSS[CSS.find(".ui-switch-track {") : CSS.find(".ui-switch-track {") + 320]
        self.assertIn("overflow: hidden", track)
        self.assertNotIn("translateX(21px)", CSS)
        self.assertNotIn("translateX(-21px)", CSS)


class SelectVerticalCenterTests(unittest.TestCase):
    def test_toggle_label_vertically_centered(self):
        self.assertIn(".ui-select-toggle {\n  display: inline-flex;\n  align-items: center;", CSS)
        self.assertIn("line-height: 1;\n  text-align: right;", CSS)
        label = CSS[CSS.find(".ui-select-label {") : CSS.find(".ui-select-label {") + 280]
        self.assertIn("align-items: center", label)
        self.assertIn("display: flex", label)


class TgPreviewChromeTests(unittest.TestCase):
    def test_captions_removed(self):
        self.assertNotIn("update-card-caption", CHAT_PREVIEW)
        self.assertNotIn("tg-preview-hint", CHAT_PREVIEW)
        self.assertNotIn("pv-hint", CHAT_PREVIEW)
        self.assertNotIn("update-card-caption", AP_PREVIEW)
        self.assertNotIn("tg-preview-hint", AP_PREVIEW)

    def test_preview_shorter(self):
        self.assertIn("min-height: 400px", CSS)
        self.assertNotIn("min-height: 520px", CSS)

    def test_mobile_preview_buttons_full_width(self):
        self.assertIn(".tg-preview-gate > .actions", CSS)
        self.assertIn(".tg-preview-gate > .actions > .btn", CSS)
        self.assertIn(".tg-preview-close-btn", CSS)
        # Desktop toolbar close is already full width
        between = CSS.split(".tg-preview-toolbar", 1)[1].split(".tg-preview-wrap", 1)[0]
        self.assertIn("width: 100%", between)
        # Mobile primary-actions block includes gate buttons
        mobile = CSS.split("/* Primary action rows:", 1)[1].split(".search-bar {", 1)[0]
        self.assertIn("tg-preview-gate > .actions", mobile)
        self.assertIn("tg-preview-gate > .actions > .btn", mobile)


class DndColsGapTests(unittest.TestCase):
    def test_active_pool_gap_tighter(self):
        m = re.search(r"(?ms)^\.dnd-cols\s*\{([^}]+)\}", CSS, re.M)
        self.assertIsNotNone(m)
        self.assertIn("gap: var(--space-2)", m.group(1))
        self.assertNotIn("gap: var(--section-gap)", m.group(1))


if __name__ == "__main__":
    unittest.main()
