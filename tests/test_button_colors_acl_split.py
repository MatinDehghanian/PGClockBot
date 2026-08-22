"""Button color catalog ACL, admin/reseller split, plan-kind inheritance."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


class ButtonColorsCatalogSplitTests(unittest.TestCase):
    def test_reseller_buttons_not_under_admin_group(self):
        from app.services.button_styles import BUTTON_STYLE_CATALOG

        by_id = {i["id"]: i for i in BUTTON_STYLE_CATALOG}
        for bid in (
            "res_orders",
            "res_payments",
            "res_renew",
            "res_buy_gb",
            "res_buy_users",
            "res_dash",
        ):
            self.assertEqual(by_id[bid]["group"], "منوی نماینده", bid)

        admin_ids = {i["id"] for i in BUTTON_STYLE_CATALOG if i["group"] == "منوی ادمین"}
        self.assertTrue(admin_ids)
        self.assertTrue(all(i.startswith("adm_") for i in admin_ids))

    def test_sectioned_catalog_separates_admin_and_reseller(self):
        from app.services.button_styles import sectioned_catalog

        sections = sectioned_catalog()
        ids = [s[0] for s in sections]
        self.assertEqual(ids, ["shared", "admin", "reseller"])
        admin_groups = {g for g, _ in sections[1][3]}
        reseller_groups = {g for g, _ in sections[2][3]}
        self.assertIn("منوی ادمین", admin_groups)
        self.assertNotIn("منوی نماینده", admin_groups)
        self.assertIn("منوی نماینده", reseller_groups)
        self.assertNotIn("منوی ادمین", reseller_groups)

        shop = sectioned_catalog(for_reseller=True)
        self.assertEqual(len(shop), 1)
        self.assertEqual(shop[0][0], "shop")
        shop_group_names = {g for g, _ in shop[0][3]}
        self.assertNotIn("منوی ادمین", shop_group_names)
        self.assertIn("منوی نماینده", shop_group_names)

    def test_reseller_catalog_includes_moved_hub_buttons(self):
        from app.services.button_styles import grouped_catalog

        ids = {item["id"] for _, items in grouped_catalog(for_reseller=True) for item in items}
        for bid in ("res_orders", "res_payments", "res_renew", "res_buy_gb", "res_buy_users"):
            self.assertIn(bid, ids)
        for bid in ("adm_dash", "adm_orders", "pg_stats", "backup_create", "plan_res_fixed"):
            self.assertNotIn(bid, ids)
        self.assertNotIn("miniapp", ids)
        self.assertNotIn("admin", ids)


class ButtonColorsAclTests(unittest.TestCase):
    def test_allowed_style_keys_blocks_admin_for_reseller(self):
        from app.services.button_styles import allowed_style_setting_keys

        owner = allowed_style_setting_keys(for_reseller=False)
        shop = allowed_style_setting_keys(for_reseller=True)
        self.assertIn("btn_style_adm_dash", owner)
        self.assertNotIn("btn_style_adm_dash", shop)
        self.assertIn("btn_style_res_orders", shop)
        self.assertIn("btn_style_shop_kind_fixed", shop)
        self.assertNotIn("btn_style_plan_res_payg", shop)
        self.assertTrue(shop.issubset(owner))

    def test_shop_settings_save_filters_colors_acl(self):
        src = (ROOT / "app/api/shop_settings.py").read_text(encoding="utf-8")
        self.assertIn("allowed_style_setting_keys(for_reseller=True)", src)
        self.assertIn('tab == "colors"', src)
        self.assertIn('startswith("btn_style_") and k not in allowed_btn', src)
        self.assertIn("sectioned_catalog(for_reseller=True)", src)

    def test_admin_settings_uses_sectioned_catalog(self):
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("sectioned_catalog()", src)
        html = (ROOT / "app/web/templates/_settings_colors.html").read_text(encoding="utf-8")
        self.assertIn("button_style_sections", html)
        self.assertIn("btn-color-section-head", html)
        self.assertNotIn("btn-color-section[", html)
        self.assertIn("زیرمنوی همان نوع", html)


class PlanKindInheritanceTests(unittest.TestCase):
    def test_plan_kind_style_id(self):
        from app.services.button_styles import plan_kind_style_id

        self.assertEqual(plan_kind_style_id("fixed"), "shop_kind_fixed")
        self.assertEqual(plan_kind_style_id("wholesale"), "shop_kind_wholesale")
        self.assertEqual(plan_kind_style_id("payg"), "plan_res_payg")
        self.assertEqual(plan_kind_style_id("res_fixed"), "plan_res_fixed")
        self.assertIsNone(plan_kind_style_id("nope"))

    def test_shop_plans_keyboard_inherits_kind_color(self):
        from app.bot.keyboards import plans_keyboard, wholesale_plans_keyboard
        from app.services.button_styles import setting_key

        plan = SimpleNamespace(id=1, name="A", price=1000, is_trial=False)
        ui = {setting_key("shop_kind_fixed"): "danger", setting_key("shop_kind_wholesale"): "success"}
        kb = plans_keyboard([plan], ui, kind="fixed", back_callback="shop:list")
        self.assertEqual(kb.inline_keyboard[0][0].style, "danger")
        wkb = wholesale_plans_keyboard([plan], ui)
        self.assertEqual(wkb.inline_keyboard[0][0].style, "success")

    def test_admin_kind_submenu_inherits(self):
        from app.bot.keyboards import admin_plans_list_keyboard, admin_reseller_plans_list_keyboard
        from app.services.button_styles import setting_key

        plan = SimpleNamespace(
            id=2,
            name="B",
            is_active=True,
            is_trial=False,
            pg_template_id=1,
            pg_group_ids="",
            commission_percent=10,
            price_per_gb=0,
        )
        ui = {
            setting_key("shop_kind_fixed"): "danger",
            setting_key("plan_res_payg"): "success",
        }
        fixed = admin_plans_list_keyboard([plan], ui, kind="fixed")
        self.assertEqual(fixed.inline_keyboard[0][0].style, "danger")
        payg = admin_reseller_plans_list_keyboard([plan], ui, mode="payg")
        self.assertEqual(payg.inline_keyboard[0][0].style, "success")


class PlanButtonStyleOverrideTests(unittest.TestCase):
    def test_parse_plan_button_style_form(self):
        from app.services.button_styles import parse_plan_button_style_form

        self.assertIsNone(parse_plan_button_style_form({"button_style": "inherit"}))
        self.assertIsNone(parse_plan_button_style_form({"button_style": "__inherit__"}))
        self.assertEqual(parse_plan_button_style_form({"button_style": "primary"}), "primary")
        self.assertEqual(parse_plan_button_style_form({"button_style": "danger"}), "danger")
        self.assertEqual(parse_plan_button_style_form({"button_style": ""}), "")
        self.assertEqual(parse_plan_button_style_form({"button_style": "hacked"}), "")

    def test_parse_plan_button_style_callback(self):
        from app.services.button_styles import parse_plan_button_style_callback

        self.assertIsNone(parse_plan_button_style_callback("inherit"))
        self.assertIsNone(parse_plan_button_style_callback("default"))
        self.assertEqual(parse_plan_button_style_callback("success"), "success")
        self.assertEqual(parse_plan_button_style_callback("bogus"), "")

    def test_resolve_plan_button_style_override(self):
        from app.services.button_styles import resolve_plan_button_style, setting_key

        ui = {setting_key("shop_kind_fixed"): "primary"}
        inherited = SimpleNamespace(id=1, button_style=None, is_trial=False)
        self.assertEqual(
            resolve_plan_button_style(ui, inherited, kind="fixed", audience="users"),
            "primary",
        )
        override = SimpleNamespace(id=2, button_style="danger", is_trial=False)
        self.assertEqual(
            resolve_plan_button_style(ui, override, kind="fixed", audience="users"),
            "danger",
        )
        white = SimpleNamespace(id=3, button_style="", is_trial=False)
        self.assertIsNone(resolve_plan_button_style(ui, white, kind="fixed", audience="users"))

    def test_plans_keyboard_uses_per_plan_override(self):
        from app.bot.keyboards import plans_keyboard
        from app.services.button_styles import setting_key

        plan = SimpleNamespace(id=9, name="VIP", price=1000, is_trial=False, button_style="success")
        ui = {setting_key("shop_kind_fixed"): "danger"}
        kb = plans_keyboard([plan], ui, kind="fixed", back_callback="shop:list")
        self.assertEqual(kb.inline_keyboard[0][0].style, "success")

    def test_reseller_api_persists_button_style(self):
        src = (ROOT / "app/api/reseller_pages.py").read_text(encoding="utf-8")
        self.assertIn("parse_plan_button_style_form", src)
        self.assertIn("plan.button_style = button_style", src)


class SecurityLeakRegressionTests(unittest.TestCase):
    def test_notify_and_btn_style_smuggle_guards_present(self):
        src = (ROOT / "app/api/shop_settings.py").read_text(encoding="utf-8")
        self.assertIn("Never allow notify_* smuggling", src)
        self.assertIn("Never allow admin-only btn_style_* smuggling", src)
        self.assertIn("ResellerSetting", src)

    def test_get_all_settings_shop_isolation_comment(self):
        src = (ROOT / "app/services/users.py").read_text(encoding="utf-8")
        self.assertIn("Never inherit live platform Setting rows", src)
        self.assertIn("Shop isolation", src)


if __name__ == "__main__":
    unittest.main()
