"""Plan categories + customer service addon packs — scope isolation & note parsing."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.db.models import Plan, PlanCategory, ServiceAddonPack
from app.services.plan_categories import (
    category_belongs_to_staff,
    category_matches_shop,
)
from app.services.service_addons import (
    KIND_DURATION,
    KIND_VOLUME,
    amount_label,
    format_addon_note,
    format_amount_label,
    is_addon_order,
    pack_belongs_to_staff,
    pack_matches_shop,
    parse_addon_note,
)
from app.services.orders import (
    fulfill_paid_order,
    is_addon_order_note,
    is_mutation_order_note,
)


def _staff(*, role: str, bot_user_id: int | None = None) -> dict:
    s: dict = {"role": role}
    if bot_user_id is not None:
        s["bot_user_id"] = bot_user_id
    if role == "admin":
        # Explicit Owner principal (is_platform_admin / is_explicit_owner_staff)
        s.update(
            {
                "org_principal_id": 1,
                "org_depth": 0,
                "org_parent_id": None,
                "org_status": "active",
                "pg_is_owner": True,
            }
        )
    return s


class PlanCategoryScopeTests(unittest.TestCase):
    def test_platform_category_owner_only(self):
        cat = PlanCategory(id=1, name="A", owner_reseller_id=None, is_active=True)
        self.assertTrue(category_belongs_to_staff(cat, _staff(role="admin")))
        self.assertFalse(
            category_belongs_to_staff(cat, _staff(role="reseller", bot_user_id=9))
        )
        self.assertTrue(category_matches_shop(cat, None))
        self.assertFalse(category_matches_shop(cat, 9))

    def test_reseller_category_isolated(self):
        cat = PlanCategory(id=2, name="B", owner_reseller_id=42, is_active=True)
        self.assertFalse(category_belongs_to_staff(cat, _staff(role="admin")))
        self.assertTrue(
            category_belongs_to_staff(cat, _staff(role="reseller", bot_user_id=42))
        )
        self.assertFalse(
            category_belongs_to_staff(cat, _staff(role="reseller", bot_user_id=7))
        )
        self.assertTrue(category_matches_shop(cat, 42))
        self.assertFalse(category_matches_shop(cat, None))


class ServiceAddonScopeTests(unittest.TestCase):
    def test_pack_scope(self):
        pack = ServiceAddonPack(
            id=1,
            name="10G",
            kind=KIND_VOLUME,
            amount=10,
            price=1000,
            owner_reseller_id=None,
            is_active=True,
        )
        self.assertTrue(pack_belongs_to_staff(pack, _staff(role="admin")))
        self.assertFalse(
            pack_belongs_to_staff(pack, _staff(role="reseller", bot_user_id=3))
        )
        shop = ServiceAddonPack(
            id=2,
            name="7d",
            kind=KIND_DURATION,
            amount=7,
            price=2000,
            owner_reseller_id=5,
            is_active=True,
        )
        self.assertTrue(pack_matches_shop(shop, 5))
        self.assertFalse(pack_matches_shop(shop, None))
        self.assertFalse(pack_matches_shop(shop, 9))

    def test_note_parse_snapshot_and_legacy(self):
        self.assertEqual(
            parse_addon_note("svc_addon:12:34:volume:10"),
            (12, 34, "volume", 10.0),
        )
        self.assertEqual(
            parse_addon_note("svc_addon:12:34:duration:7"),
            (12, 34, "duration", 7.0),
        )
        # Legacy notes without snapshot still parse
        self.assertEqual(parse_addon_note("svc_addon:12:34"), (12, 34, None, None))
        self.assertIsNone(parse_addon_note("renew:1"))
        note = format_addon_note(3, 9, kind=KIND_VOLUME, amount=2.5)
        self.assertEqual(parse_addon_note(note), (3, 9, "volume", 2.5))
        self.assertTrue(is_addon_order_note("svc_addon:1:2:volume:1"))
        self.assertTrue(is_mutation_order_note("svc_addon:1:2:duration:7"))
        self.assertTrue(is_mutation_order_note("renew:9"))
        self.assertFalse(is_mutation_order_note("wholesale:2"))
        pack = ServiceAddonPack(
            id=1, name="x", kind=KIND_VOLUME, amount=10, price=1, is_active=True
        )
        self.assertIn("گیگ", amount_label(pack))
        self.assertIn("روز", format_amount_label(KIND_DURATION, 7))
        order = MagicMock()
        order.note = "svc_addon:1:2:volume:10"
        self.assertTrue(is_addon_order(order))

    def test_fulfill_paid_order_exported(self):
        self.assertTrue(callable(fulfill_paid_order))


class WiringTests(unittest.TestCase):
    def test_templates_and_routes(self):
        from pathlib import Path

        plans = Path("app/web/templates/plans.html").read_text(encoding="utf-8")
        self.assertIn("modal-plan-categories", plans)
        self.assertIn("modal-service-addons", plans)
        self.assertIn("برچسب دسته", plans)
        self.assertIn("بسته حجم/زمان", plans)
        self.assertIn('name="category_id"', plans)
        # Existing plan kinds (ثابت/…) must remain; labels are additive
        self.assertIn("USER_KINDS", plans)
        self.assertIn("{value: 'fixed', label: 'ثابت'}", plans)
        self.assertIn("data-category-edit", plans)
        self.assertIn("data-addon-edit", plans)
        self.assertIn("service-addon-kind", plans)
        extras = Path("app/api/plan_catalog_extras.py").read_text(encoding="utf-8")
        self.assertIn('/plans/categories', extras)
        self.assertIn('/plans/addons', extras)
        self.assertIn("/edit", extras)
        app = Path("app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("register_plan_catalog_extras", app)
        self.assertIn("is_mutation_order_note", app)
        self.assertIn("fulfill_paid_order", app)
        models = Path("app/db/models.py").read_text(encoding="utf-8")
        self.assertIn("class PlanCategory", models)
        self.assertIn("class ServiceAddonPack", models)
        self.assertIn("category_id", models)
        mig = Path(
            "alembic/versions/0031_plan_categories_service_addons.py"
        ).read_text(encoding="utf-8")
        self.assertIn("0030_legacy_wallet_isolation_repair", mig)
        svc = Path("app/bot/handlers/services.py").read_text(encoding="utf-8")
        self.assertIn("svc:addon:", svc)
        self.assertIn("create_addon_order", svc)
        addons = Path("app/services/service_addons.py").read_text(encoding="utf-8")
        self.assertIn("format_addon_note", addons)
        self.assertIn("حجم نامحدود", addons)

    def test_bot_manage_parity_wiring(self):
        """Admin/reseller bot hubs expose category + addon manage (web parity)."""
        from pathlib import Path

        from app.bot import keyboards as kb

        aud = dict(kb._admin_plans_audience_entries())
        listing = dict(kb._admin_plans_list_entries())
        res = dict(kb._reseller_plans_submenu_entries())
        self.assertEqual(aud.get(kb.REPLY_ACTION_ADM_PLANS_CATEGORIES), "🏷 برچسب دسته")
        self.assertEqual(aud.get(kb.REPLY_ACTION_ADM_PLANS_ADDONS), "⏱ بسته حجم/زمان")
        self.assertIn(kb.REPLY_ACTION_ADM_PLANS_CATEGORIES, listing)
        self.assertIn(kb.REPLY_ACTION_ADM_PLANS_ADDONS, listing)
        self.assertEqual(res.get(kb.REPLY_ACTION_RES_PLAN_CATEGORIES), "🏷 برچسب دسته")
        self.assertEqual(res.get(kb.REPLY_ACTION_RES_PLAN_ADDONS), "⏱ بسته حجم/زمان")

        manage = Path("app/bot/handlers/plan_catalog_manage.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("create_category", manage)
        self.assertIn("delete_category", manage)
        self.assertIn("create_pack", manage)
        self.assertIn("delete_pack", manage)
        self.assertIn("resolve_catalog_staff", manage)
        self.assertIn("user_safe_error", manage)
        self.assertIn("pcm:cat:", manage)
        self.assertIn("pcm:addon:", manage)

        admin = Path("app/bot/handlers/admin.py").read_text(encoding="utf-8")
        self.assertIn("adm:plan:newcat:", admin)
        self.assertIn("adm:plan:catpick:", admin)
        self.assertIn("adm:plan:setcat:", admin)
        self.assertIn("pending_category_id", admin)
        self.assertIn("resolve_category_for_plan_write", admin)
        self.assertIn("add_plan_category", admin)

        res_plans = Path("app/bot/handlers/reseller_plans.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("res:plan:newcat:", res_plans)
        self.assertIn("res:plan:catpick:", res_plans)
        self.assertIn("res:plan:setcat:", res_plans)
        self.assertIn("category_id", res_plans)
        self.assertIn("resolve_category_for_plan_write", res_plans)

        nav = Path("app/bot/handlers/reply_nav.py").read_text(encoding="utf-8")
        self.assertIn("REPLY_ACTION_ADM_PLANS_CATEGORIES", nav)
        self.assertIn("REPLY_ACTION_ADM_PLANS_ADDONS", nav)
        self.assertIn("REPLY_ACTION_RES_PLAN_CATEGORIES", nav)
        self.assertIn("open_categories_manage", nav)
        self.assertIn("open_addons_manage", nav)

        init = Path("app/bot/__init__.py").read_text(encoding="utf-8")
        self.assertIn("plan_catalog_manage", init)

        labels = Path("app/services/settings_button_labels.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("btn_svc_addon", labels)


class PlanModelFieldTests(unittest.TestCase):
    def test_plan_has_category_attr(self):
        p = Plan(name="t", price=1, duration_days=30)
        self.assertTrue(hasattr(p, "category_id"))


class ApplyServiceAddonUnpackTests(unittest.IsolatedAsyncioTestCase):
    async def test_apply_accepts_four_tuple_snapshot_note(self):
        """Regression: parse_addon_note returns 4 values — unpack must not crash."""
        from unittest.mock import AsyncMock, patch

        from app.db.models import OrderStatus
        from app.services.service_addons import apply_service_addon

        order = MagicMock()
        order.id = 99
        order.note = "svc_addon:1:2:volume:10"
        order.status = OrderStatus.PAID.value
        order.service_id = 2
        order.user_id = 7
        order.reseller_id = None

        session = AsyncMock()
        # Claim PAID → DELIVERING succeeds once
        claim_result = MagicMock()
        claim_result.rowcount = 1
        session.execute = AsyncMock(return_value=claim_result)
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        # Pack/service missing → ValueError after successful unpack
        session.get = AsyncMock(return_value=None)

        with patch(
            "app.services.service_addons.update", return_value=MagicMock()
        ):
            with self.assertRaises(ValueError) as ctx:
                await apply_service_addon(session, order)
        self.assertIn("بسته یا سرویس", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
