"""Regression tests for 2.6.13 UI / force-join / welcome image."""

from __future__ import annotations

import unittest
from pathlib import Path


class PlansTitleActionsTests(unittest.TestCase):
    def test_buttons_under_title_stacked(self):
        """Plans actions sit under the title (3.2.4 layout) with 3.2.3 spacing tokens."""
        html = Path("app/web/templates/plans.html").read_text(encoding="utf-8")
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        head = html.split("{% block content %}", 1)[1].split("{% if flash_ok %}", 1)[0]
        self.assertIn("page-head--stack", head)
        self.assertIn("page-title-actions", head)
        self.assertIn('data-modal-open="modal-trial"', head)
        # stacked actions are inside the title column, not a sibling .actions row
        self.assertNotIn(
            '</div>\n  <div class="actions">\n    <button type="button" class="btn" data-modal-open="modal-trial"',
            head,
        )
        actions = css.split(".page-title-actions {", 1)[1].split("}", 1)[0]
        self.assertIn("var(--space-1)", actions)
        self.assertIn("margin-top: var(--space-1)", actions)


class UploadBoxContrastTests(unittest.TestCase):
    def test_image_setting_matches_body(self):
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        block = css.split(".image-setting {\n  display: flex; flex-direction: column; gap: var(--space-1);", 1)[1]
        block = block.split("}", 1)[0]
        self.assertIn("background: var(--background);", block)

    def test_upload_outer_body_color(self):
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        block = css.split(".upload-box {", 1)[1].split(".upload-box:hover", 1)[0]
        self.assertIn("background: var(--background);", block)


class ForceJoinEntriesTests(unittest.TestCase):
    def test_legacy_lines_all_required(self):
        from app.services.users import parse_force_join_channels, parse_force_join_entries

        self.assertEqual(
            parse_force_join_channels("@a\n@b, @c\n@a"),
            ["@a", "@b", "@c"],
        )
        entries = parse_force_join_entries("@a\n@b")
        self.assertEqual(entries, [{"id": "@a", "required": True}, {"id": "@b", "required": True}])

    def test_json_required_filter(self):
        from app.services.users import (
            normalize_force_join_channel_value,
            parse_force_join_channels,
            parse_force_join_entries,
        )

        raw = '[{"id":"@must","required":true},{"id":"@opt","required":false}]'
        self.assertEqual(parse_force_join_channels(raw), ["@must"])
        entries = parse_force_join_entries(raw)
        self.assertEqual(len(entries), 2)
        self.assertFalse(entries[1]["required"])
        norm = normalize_force_join_channel_value("@x\n@y")
        self.assertIn('"id": "@x"', norm)
        self.assertIn('"required": true', norm)

    def test_settings_field_ui(self):
        html = Path("app/web/templates/_settings_field.html").read_text(encoding="utf-8")
        js = Path("app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("force_channels", html)
        self.assertIn("data-force-channels", html)
        # Add button is injected by panel.js (not static HTML)
        self.assertIn("data-force-channels-add", js)
        self.assertIn("عضویت الزامی", js)


class BroadcastKebabTests(unittest.TestCase):
    def test_direct_delete_no_kebab(self):
        html = Path("app/web/templates/broadcast.html").read_text(encoding="utf-8")
        self.assertNotIn("row_actions", html)
        self.assertIn("btn-danger", html)


class WelcomeImageTests(unittest.TestCase):
    def test_welcome_image_removed(self):
        from app.services.users import DEFAULT_SETTINGS, IMAGE_KEYS, SETTING_GROUPS

        self.assertNotIn("welcome_image", DEFAULT_SETTINGS)
        self.assertNotIn("welcome_image", IMAGE_KEYS)
        welcome_fields = SETTING_GROUPS["خوش‌آمد و هویت"]
        keys = [f[0] for f in welcome_fields]
        self.assertNotIn("welcome_image", keys)
        ap = Path("app/web/templates/_settings_appearance.html").read_text(encoding="utf-8")
        self.assertNotIn('name="welcome_image"', ap)
        src = Path("app/bot/handlers/start.py").read_text(encoding="utf-8")
        self.assertNotIn("welcome_image", src)
        self.assertNotIn("answer_photo", src)


if __name__ == "__main__":
    unittest.main()
