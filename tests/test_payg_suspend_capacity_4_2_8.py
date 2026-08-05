"""PAYG suspend + reseller capacity add-ons tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.billing import BILLING_MODE_PAYG, payg_purchase_min_wallet
from app.services.reseller_capacity import (
    plan_allows_buy_extra,
    plan_extra_gb_price,
    plan_renew_price,
)


class PaygSuspendHelpersTests(unittest.IsolatedAsyncioTestCase):
    async def test_min_topup_is_2x_threshold(self):
        from app.services.billing_suspend import min_topup_to_unsuspend

        with patch(
            "app.services.billing_suspend.get_low_balance_threshold",
            AsyncMock(return_value=10_000),
        ):
            need = await min_topup_to_unsuspend(AsyncMock())
        self.assertEqual(need, 20_000)

    async def test_assert_topup_when_suspended(self):
        from app.services.billing import BillingError
        from app.services.billing_suspend import assert_topup_clears_suspend

        profile = MagicMock()
        profile.billing_suspended_at = object()
        with patch(
            "app.services.billing_suspend.min_topup_to_unsuspend",
            AsyncMock(return_value=20_000),
        ):
            with self.assertRaises(BillingError):
                await assert_topup_clears_suspend(AsyncMock(), profile, 5_000)

    def test_purchase_min_still_strict(self):
        self.assertEqual(payg_purchase_min_wallet(10_000), 20_001)


class ResellerCapacityPlanTests(unittest.TestCase):
    def test_allow_flag(self):
        plan = MagicMock(allow_buy_extra=True, extra_gb_price=1500, renew_price=0, price=50_000)
        self.assertTrue(plan_allows_buy_extra(plan))
        self.assertEqual(plan_extra_gb_price(plan), 1500)
        self.assertEqual(plan_renew_price(plan), 50_000)

    def test_renew_price_override(self):
        plan = MagicMock(renew_price=12_000, price=50_000)
        self.assertEqual(plan_renew_price(plan), 12_000)

    def test_templates_have_extra_switch(self):
        plans = Path("app/web/templates/plans.html").read_text(encoding="utf-8")
        edit = Path("app/web/templates/reseller_plan_edit.html").read_text(encoding="utf-8")
        self.assertIn("allow_buy_extra", plans)
        self.assertIn("extra_gb_price", plans)
        self.assertIn("allow_buy_extra", edit)
        self.assertIn("extra_user_price", edit)

    def test_keyboard_capacity_entries(self):
        from app.bot.keyboards import _reseller_submenu_entries

        plan_on = MagicMock(allow_buy_extra=True)
        profile = MagicMock(billing_mode=BILLING_MODE_PAYG, plan=plan_on)
        with patch("app.services.authz.shop_feature_allowed", return_value=True):
            labels = [t for _, t in _reseller_submenu_entries(profile)]
        self.assertIn("📦 خرید حجم اضافه", labels)
        self.assertIn("👤 خرید کاربر اضافه", labels)
        self.assertIn("🔄 تمدید سرویس", labels)

        plan_off = MagicMock(allow_buy_extra=False)
        profile.plan = plan_off
        with patch("app.services.authz.shop_feature_allowed", return_value=True):
            labels2 = [t for _, t in _reseller_submenu_entries(profile)]
        self.assertNotIn("📦 خرید حجم اضافه", labels2)
        self.assertIn("🔄 تمدید سرویس", labels2)


class SchemaAddonTests(unittest.TestCase):
    def test_model_fields(self):
        from app.db.models import ResellerPlan, ResellerProfile

        self.assertTrue(hasattr(ResellerProfile, "billing_suspended_at"))
        self.assertTrue(hasattr(ResellerPlan, "allow_buy_extra"))
        self.assertTrue(hasattr(ResellerPlan, "extra_gb_price"))

    def test_migrate_script(self):
        src = Path("app/db/session.py").read_text(encoding="utf-8")
        self.assertIn("billing_suspended_at", src)
        self.assertIn("allow_buy_extra", src)
        alem = Path("alembic/versions/0005_payg_suspend_plan_addons.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("billing_suspended_user_ids", alem)


if __name__ == "__main__":
    unittest.main()
