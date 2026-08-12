"""UX20 feature unit tests — helpers, settings, templates, clone/gift/funnel."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ux20 import (
    FUNNEL_STEPS,
    bot_deep_link,
    capacity_should_warn,
    compute_user_risk_flags,
    generate_charge_code,
    normalize_charge_code,
    parse_risk_flags,
    serialize_risk_flags,
    shop_bundle_to_json,
)


class Ux20HelpersTests(unittest.TestCase):
    def test_charge_code_normalize(self):
        self.assertEqual(normalize_charge_code("  ab cd-1 "), "ABCD-1")
        self.assertTrue(generate_charge_code("gift").startswith("GIFT-"))

    def test_risk_flags(self):
        self.assertEqual(parse_risk_flags("multi_trial, manual"), ["multi_trial", "manual"])
        self.assertEqual(serialize_risk_flags(["manual", "manual"]), "manual")
        flags = compute_user_risk_flags(
            trial_count=2, rejected_payments=3, open_tickets=3, existing=["manual"]
        )
        self.assertIn("multi_trial", flags)
        self.assertIn("repeat_reject", flags)
        self.assertIn("many_tickets", flags)
        self.assertIn("manual", flags)

    def test_capacity_warn(self):
        self.assertTrue(capacity_should_warn([{"pct": 85}], 80))
        self.assertFalse(capacity_should_warn([{"pct": 50}], 80))
        self.assertFalse(capacity_should_warn([None], 80))

    def test_deep_link(self):
        self.assertEqual(
            bot_deep_link("MyBot", "renew"),
            "https://t.me/MyBot?start=renew",
        )
        self.assertIsNone(bot_deep_link("", "wallet"))

    def test_funnel_steps(self):
        self.assertIn("shop_open", FUNNEL_STEPS)
        self.assertIn("delivered", FUNNEL_STEPS)

    def test_shop_bundle_json(self):
        raw = shop_bundle_to_json({"format": "pgclock-shop-bundle", "version": 1})
        self.assertIn("pgclock-shop-bundle", raw)


class Ux20SettingsCatalogTests(unittest.TestCase):
    def test_default_settings_keys(self):
        from app.services.users import DEFAULT_SETTINGS, SETTING_GROUPS, TAB_SETTING_GROUPS

        for key in (
            "shop_maintenance_enabled",
            "admin_daily_report_enabled",
            "backup_schedule_enabled",
            "capacity_warn_pct",
            "receipt_auto_match_enabled",
            "brand_primary_color",
            "funnel_tracking_enabled",
            "one_tap_renew_enabled",
        ):
            self.assertIn(key, DEFAULT_SETTINGS)
        self.assertIn("حالت تعمیرات و رسید", SETTING_GROUPS)
        self.assertIn("گزارش و عملیات", SETTING_GROUPS)
        self.assertIn("بکاپ زمان‌بندی", SETTING_GROUPS)
        self.assertIn("حالت تعمیرات و رسید", TAB_SETTING_GROUPS["payment"])
        self.assertIn("بکاپ زمان‌بندی", TAB_SETTING_GROUPS["backup"])


class Ux20TemplatePresenceTests(unittest.TestCase):
    def test_templates_exist(self):
        root = Path("app/web/templates")
        for name in (
            "gift_codes.html",
            "magic_links.html",
            "funnel.html",
            "home.html",
            "reseller_home.html",
            "finance.html",
        ):
            self.assertTrue((root / name).is_file(), name)

    def test_home_has_quick_open_and_action_center(self):
        home = Path("app/web/templates/home.html").read_text(encoding="utf-8")
        self.assertIn("ورود به پاسارگارد", home)
        self.assertIn("مرکز اقدام امروز", home)
        self.assertIn("home-pg-health", home)
        self.assertIn("tools/gift-codes", home)

    def test_finance_delivery_tab(self):
        html = Path("app/web/templates/finance.html").read_text(encoding="utf-8")
        self.assertIn("تحویل ناموفق", html)
        self.assertIn("retry-delivery", html)

    def test_plans_clone_button(self):
        html = Path("app/web/templates/plans.html").read_text(encoding="utf-8")
        self.assertIn("/plans/{{ p.id }}/clone", html)

    def test_preview_simulator(self):
        html = Path("app/web/templates/_tg_preview_chat.html").read_text(encoding="utf-8")
        js = Path("app/web/templates/_tg_preview_chat_js.html").read_text(encoding="utf-8")
        self.assertIn("pv-sim-buy", html)
        self.assertIn("شبیه‌ساز خرید", html)
        self.assertIn("simStep", js)

    def test_backup_verify_ui(self):
        html = Path("app/web/templates/_settings_backup.html").read_text(encoding="utf-8")
        self.assertIn("/backup/verify-last", html)
        self.assertIn("backup-schedule-form", html)


class Ux20ModelsMigrationTests(unittest.TestCase):
    def test_models_have_new_fields(self):
        from app.db import models

        self.assertTrue(hasattr(models.BotUser, "staff_note"))
        self.assertTrue(hasattr(models.BotUser, "risk_flags"))
        self.assertTrue(hasattr(models.Order, "staff_note"))
        self.assertTrue(hasattr(models.UserService, "renew_nudge_sent_at"))
        self.assertTrue(hasattr(models.ResellerProfile, "capacity_warned_at"))
        self.assertTrue(hasattr(models, "DeliveryFailure"))
        self.assertTrue(hasattr(models, "ChargeCode"))
        self.assertTrue(hasattr(models, "FunnelEvent"))

    def test_alembic_revision_chain(self):
        text = Path("alembic/versions/0009_ux20_ops_features.py").read_text(encoding="utf-8")
        self.assertIn('revision: str = "0009_ux20_ops_features"', text)
        self.assertIn("0008_loyalty_discounts", text)


class Ux20RoutesRegistrationTests(unittest.TestCase):
    def test_ux20_pages_registered(self):
        src = Path("app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("register_ux20_pages", src)

    def test_scheduler_jobs(self):
        src = Path("app/jobs/scheduler.py").read_text(encoding="utf-8")
        self.assertIn("run_scheduled_backup", src)
        self.assertIn("run_admin_daily_report", src)
        self.assertIn("scheduled_backup", src)


class Ux20AsyncServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_clone_plan_permission(self):
        from app.services.ux20 import clone_plan

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)
        with self.assertRaises(ValueError):
            await clone_plan(session, 1, owner_reseller_id=None)

    async def test_action_center_shape(self):
        from app.services.ux20 import build_action_center

        session = AsyncMock()

        async def _exec(q):
            m = MagicMock()
            # count queries return scalar
            m.scalar.return_value = 0
            m.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=_exec)
        out = await build_action_center(session, reseller_id=None, expire_days=3)
        self.assertIn("items", out)
        self.assertFalse(out["has_items"])


class Ux20VersionTests(unittest.TestCase):
    def test_version_aligned(self):
        from app.version import __version__

        self.assertEqual(Path("VERSION").read_text().strip(), "5.1.0")
        self.assertEqual(__version__, "5.1.0")
        notes = Path("app/services/release_notes.py").read_text(encoding="utf-8")
        self.assertIn('"5.1.0"', notes)


if __name__ == "__main__":
    unittest.main()
