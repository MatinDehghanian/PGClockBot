"""Panel UI: menu card gaps + ui-select vertical center (root causes)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from css_blocks import rule

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
        toggle = rule(CSS, ".ui-select-toggle")
        self.assertIn("display: inline-flex;", toggle)
        self.assertIn("align-items: center;", toggle)
        self.assertIn("line-height: 1;", toggle)
        label = rule(CSS, ".ui-select-label")
        self.assertIn("align-items: center", label)
        self.assertIn("display: flex", label)
        self.assertIn("margin: 0;", label)
        self.assertIn("line-height: 1;", label)
        self.assertIn("font-size: inherit;", label)

    def test_menu_layout_title_span_does_not_target_ui_select_label(self):
        """Regression: `.setting-item span` matched `.ui-select-label` and broke centering."""
        # Broad selector must not exist
        self.assertNotRegex(
            CSS,
            r"\.menu-layout-mode\s+\.setting-item\s+span\s*\{",
        )
        title = rule(CSS, ".menu-layout-mode .setting-item > span:not(.ui-select-label)")
        self.assertIn("font-size: 12px;", title)
        self.assertIn("margin-bottom: var(--space-1);", title)


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
        between = CSS.split(".tg-preview-toolbar", 1)[1].split(".tg-preview-wrap", 1)[0]
        self.assertIn("width: 100%", between)
        mobile = CSS.split("/* Primary action rows:", 1)[1].split(".search-bar {", 1)[0]
        self.assertIn("tg-preview-gate > .actions", mobile)
        self.assertIn("tg-preview-gate > .actions > .btn", mobile)


class MenuCardGapTests(unittest.TestCase):
    def test_card_stacks_use_stack_gap(self):
        """Preview↔layout uses --stack-gap; other menu boxes must match."""
        main = rule(CSS, ".settings-main")
        self.assertIn("gap: var(--stack-gap);", main)
        form = rule(CSS, ".settings-form,\nform.settings-form,\n.menu-layout-form")
        self.assertIn("gap: var(--stack-gap);", form)
        dnd = rule(CSS, ".dnd-cols")
        self.assertIn("gap: var(--stack-gap);", dnd)
        self.assertNotIn("gap: var(--section-gap)", dnd)

    def test_dnd_cards_zero_margin(self):
        nested = rule(CSS, ".dnd-cols > .card,\n.dnd-cols > .dnd-card")
        self.assertIn("margin-bottom: 0;", nested)
        # Mobile must not re-stack section-gap margin on nested cards
        self.assertIn(".dnd-cols > .card,", CSS)
        mobile_bit = CSS.split("@media (max-width: 900px)", 1)[1]
        # First mobile block that contains the dash-cols / card margin rule
        self.assertIn(".dnd-cols > .dnd-card,", mobile_bit)
        self.assertRegex(
            mobile_bit,
            r"\.dnd-cols\s*>\s*\.card,[\s\S]*?margin-bottom:\s*0;",
        )


if __name__ == "__main__":
    unittest.main()
