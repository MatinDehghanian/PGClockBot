"""Tests for Telegram bot appearance helpers."""

from __future__ import annotations

import unittest

from app.services.bot_appearance import (
    DESCRIPTION_MAX,
    NAME_MAX,
    SHORT_DESCRIPTION_MAX,
    appearance_to_form_dict,
    clip,
    validate_appearance_form,
    BotAppearance,
)


class ClipTests(unittest.TestCase):
    def test_clip_trims_and_limits(self):
        self.assertEqual(clip("  abc  ", 2), "ab")
        self.assertEqual(clip(None, 5), "")


class ValidateTests(unittest.TestCase):
    def test_ok(self):
        self.assertIsNone(
            validate_appearance_form(
                name="Clock",
                description="about",
                short_description="hi",
                cmd_start="start",
                cmd_help="help",
            )
        )

    def test_name_too_long(self):
        err = validate_appearance_form(
            name="x" * (NAME_MAX + 1),
            description="",
            short_description="",
            cmd_start="a",
            cmd_help="b",
        )
        self.assertIn("نام", err or "")

    def test_description_too_long(self):
        err = validate_appearance_form(
            name="n",
            description="d" * (DESCRIPTION_MAX + 1),
            short_description="",
            cmd_start="a",
            cmd_help="b",
        )
        self.assertIn("کپشن", err or "")

    def test_short_too_long(self):
        err = validate_appearance_form(
            name="n",
            description="",
            short_description="s" * (SHORT_DESCRIPTION_MAX + 1),
            cmd_start="a",
            cmd_help="b",
        )
        self.assertIn("وسط", err or "")

    def test_commands_required(self):
        err = validate_appearance_form(
            name="n",
            description="",
            short_description="",
            cmd_start="",
            cmd_help="b",
        )
        self.assertIn("/start", err or "")


class FormDictTests(unittest.TestCase):
    def test_maps_fields(self):
        app = BotAppearance(
            name="A",
            username="bot",
            description="D",
            short_description="S",
            cmd_start="st",
            cmd_help="hp",
        )
        d = appearance_to_form_dict(app, local_photo="uploads/x.jpg")
        self.assertEqual(d["bot_tg_name"], "A")
        self.assertEqual(d["bot_username"], "bot")
        self.assertEqual(d["bot_tg_photo"], "uploads/x.jpg")
        self.assertEqual(d["bot_cmd_start"], "st")


class TabsTests(unittest.TestCase):
    def test_appearance_in_admin_and_reseller_tabs(self):
        from app.services.resellers import RESELLER_SETTINGS_TABS
        from app.services.users import SETTINGS_TABS

        self.assertIn("appearance", {t[0] for t in SETTINGS_TABS})
        self.assertIn("appearance", {t[0] for t in RESELLER_SETTINGS_TABS})


if __name__ == "__main__":
    unittest.main()
