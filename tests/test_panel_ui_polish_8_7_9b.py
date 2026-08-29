"""Panel UI polish — supports bulk editor, settings completeness, motion."""

from __future__ import annotations

import unittest
from pathlib import Path

from css_blocks import at_rule, rule

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
JS = ROOT / "app/web/static/panel.js"
SUPPORTS_TPL = ROOT / "app/web/templates/_settings_supports.html"


class SupportsBulkEditorTests(unittest.TestCase):
    def test_template_matches_pay_dest_pattern(self):
        tpl = SUPPORTS_TPL.read_text(encoding="utf-8")
        self.assertIn("data-supports-editor", tpl)
        self.assertIn("data-supports-json", tpl)
        self.assertIn("data-supports-list", tpl)
        self.assertIn('name="support_contacts"', tpl)
        self.assertIn("ذخیره پشتیبان‌ها", tpl)
        self.assertNotIn("supports/delete", tpl)
        self.assertNotIn("افزودن پشتیبان", tpl)

    def test_js_bulk_editor(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("data-supports-editor", js)
        self.assertIn("data-supports-add", js)
        self.assertIn("supports-remove", js)

    def test_contacts_from_form_json(self):
        from app.services.support_contacts import contacts_from_form_json

        ok, err = contacts_from_form_json(
            '[{"title":"S","telegram":"@support_ok","sort":0,"enabled":true}]'
        )
        self.assertIsNone(err)
        self.assertEqual(len(ok), 1)
        self.assertEqual(ok[0]["telegram"], "@support_ok")

        bad, err2 = contacts_from_form_json('[{"title":"S","telegram":"x"}]')
        self.assertIsNone(bad)
        self.assertTrue(err2)


class SettingsTextsCompletenessTests(unittest.TestCase):
    def test_messages_include_titles(self):
        from app.services.users import SETTING_GROUPS

        keys = {f[0] for f in SETTING_GROUPS["متن پیام‌ها"]}
        self.assertIn("wallet_success_title", keys)
        self.assertIn("wallet_success_text", keys)
        self.assertIn("payment_ok_title", keys)
        self.assertIn("delivery_title", keys)

    def test_buttons_include_admin_and_submenus(self):
        from app.services.users import DEFAULT_SETTINGS, SETTING_GROUPS

        keys = {f[0] for f in SETTING_GROUPS["متن دکمه‌های منو"]}
        for k in (
            "btn_adm_users",
            "btn_adm_settings",
            "btn_adm_broadcast",
            "btn_wallet_topup",
            "btn_wallet_tx",
            "btn_support_new",
            "btn_support_list",
            "btn_loy_points",
            "btn_loy_rewards",
            "btn_loy_history",
        ):
            self.assertIn(k, keys)
            self.assertIn(k, DEFAULT_SETTINGS)


class TgPreviewSpacingTests(unittest.TestCase):
    def test_layout_gap_tightened(self):
        css = CSS.read_text(encoding="utf-8-sig")
        layout = rule(css, ".settings-layout")
        self.assertIn("gap: var(--stack-gap);", layout)
        preview_margins = rule(
            css,
            ".settings-layout > .tg-preview-slot > .card, "
            ".settings-layout > .tg-preview-slot > .settings-card, "
            ".settings-layout > .tg-preview-slot > .tg-preview-card",
        )
        self.assertIn("margin-bottom: 0;", preview_margins)


class DrawerMotionTests(unittest.TestCase):
    def test_side_panel_transform_slide(self):
        mobile = at_rule(CSS.read_text(encoding="utf-8-sig"), "@media (max-width: 900px)")
        panel = rule(mobile, ".side-panel")
        self.assertIn("transform: translate3d(calc(100% + 24px), 0, 0);", panel)
        open_panel = rule(mobile, ".side.open .side-panel")
        self.assertIn("transform: translate3d(0, 0, 0);", open_panel)


if __name__ == "__main__":
    unittest.main()
