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


class PlanModelFieldTests(unittest.TestCase):
    def test_plan_has_category_attr(self):
        p = Plan(name="t", price=1, duration_days=30)
        self.assertTrue(hasattr(p, "category_id"))


if __name__ == "__main__":
    unittest.main()
