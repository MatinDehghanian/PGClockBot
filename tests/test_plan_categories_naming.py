"""Sales-plan categories, Telegram naming context, and shop isolation."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.db.models import BotUser, Order, OrderStatus, Plan, UserService
from app.services.orders import generate_pg_username

ROOT = Path(__file__).resolve().parents[1]
OWNER = {
    "role": "admin", "org_principal_id": 1, "org_depth": 0,
    "org_parent_id": None, "org_status": "active",
}


class NamingContextTests(unittest.IsolatedAsyncioTestCase):
    async def name(self, volume=30, username="ali_user", telegram_id=9001, **kwargs):
        plan = SimpleNamespace(
            data_limit_gb=volume, pg_username_prefix="vip", pg_username_suffix=None,
            pg_username_pattern="{prefix}_{username}_{plan_volume}{plan_unit}_{random}",
        )
        user = SimpleNamespace(username=username, telegram_id=telegram_id)
        with patch("app.services.users.get_all_settings", AsyncMock(return_value={})), patch(
            "app.services.orders._random_alnum", return_value="a1b2c3d4"
        ):
            return await generate_pg_username(AsyncMock(), user_id=7, plan=plan, user=user, **kwargs)

    async def test_numeric_volume_and_unit_are_separate(self):
        self.assertEqual(await self.name(), "vip_ali_user_30GB_a1b2c3d4")

    async def test_fractional_volume(self):
        self.assertEqual(await self.name(volume=1.5), "vip_ali_user_1.5GB_a1b2c3d4")

    async def test_unlimited_and_zero(self):
        for volume in (None, 0):
            self.assertEqual(await self.name(volume=volume), "vip_ali_user_unlimitedGB_a1b2c3d4")

    async def test_user_without_username_uses_telegram_id(self):
        self.assertEqual(await self.name(username=None), "vip_9001_30GB_a1b2c3d4")

    async def test_at_sign_is_removed(self):
        self.assertEqual(await self.name(username="@ali_user"), "vip_ali_user_30GB_a1b2c3d4")

    async def test_global_pattern_receives_context_and_shop_scope(self):
        settings = AsyncMock(return_value={"pg_username_pattern": "{username}_{plan_volume}{plan_unit}_{random}"})
        session = AsyncMock()
        session.get.return_value = SimpleNamespace(username="shop_buyer", telegram_id=9001)
        with patch("app.services.users.get_all_settings", settings), patch(
            "app.services.orders._random_alnum", return_value="a1b2c3d4"
        ):
            name = await generate_pg_username(session, user_id=7, reseller_id=42, plan=SimpleNamespace(data_limit_gb=12))
        self.assertEqual(name, "shop_buyer_12GB_a1b2c3d4")
        settings.assert_awaited_once_with(session, reseller_id=42)
        session.get.assert_awaited_once_with(BotUser, 7)

    async def test_legacy_pattern_does_not_query_user(self):
        session = AsyncMock()
        with patch("app.services.users.get_all_settings", AsyncMock(return_value={})), patch(
            "app.services.orders._random_alnum", return_value="a1b2c3d4"
        ):
            self.assertEqual(await generate_pg_username(session, user_id=7), "clk_a1b2c3d4")
        session.get.assert_not_awaited()

    def test_new_variables_are_isolated_to_naming(self):
        from app.services.message_variables import DOMAIN_NAMING, DOMAIN_PAYMENT, render_message_template
        template = "{plan_volume}{plan_unit}_{username}_{unknown}"
        values = dict(plan_volume="30", plan_unit="GB", username="ali")
        self.assertEqual(render_message_template(template, domain=DOMAIN_NAMING, html=False, **values), "30GB_ali_{unknown}")
        self.assertEqual(render_message_template(template, domain=DOMAIN_PAYMENT, **values), template)


class CategoryKeyboardTests(unittest.TestCase):
    def plans(self):
        return [
            SimpleNamespace(id=1, name="A", price=100, category="اقتصادی", is_trial=False),
            SimpleNamespace(id=2, name="B", price=200, category="اقتصادی", is_trial=False),
            SimpleNamespace(id=3, name="C", price=300, category=None, is_trial=False),
            SimpleNamespace(id=4, name="D", price=400, category="ویژه" * 30, is_trial=False),
        ]

    def test_categories_use_existing_kind_style_and_short_callbacks(self):
        from app.bot.keyboards import plans_keyboard
        kb = plans_keyboard(self.plans(), {"btn_style_shop_kind_fixed": "danger"}, kind="fixed")
        buttons = [row[0] for row in kb.inline_keyboard]
        self.assertEqual([b.callback_data for b in buttons[:-1]], ["shop:category:fixed:1", "shop:category:fixed:0", "shop:category:fixed:4"])
        self.assertTrue(all(b.style == "danger" for b in buttons[:-1]))
        self.assertTrue(all(len(b.callback_data.encode()) <= 64 for b in buttons))

    def test_uncategorized_catalog_keeps_original_plan_rows(self):
        from app.bot.keyboards import plans_keyboard
        plans = self.plans()
        for p in plans:
            p.category = None
        kb = plans_keyboard(plans)
        self.assertEqual(kb.inline_keyboard[0][0].callback_data, "shop:plan:1")

    def test_category_contents_keep_plan_color_and_back(self):
        from app.bot.keyboards import plans_keyboard
        plans = self.plans()[:2]
        plans[0].button_style = "success"
        kb = plans_keyboard(plans, kind="fixed", show_categories=False, back_callback="shop:kind:fixed")
        self.assertEqual(kb.inline_keyboard[0][0].callback_data, "shop:plan:1")
        self.assertEqual(kb.inline_keyboard[0][0].style, "success")
        self.assertEqual(kb.inline_keyboard[-1][0].callback_data, "shop:kind:fixed")

    def test_wholesale_supports_category_and_plan_views(self):
        from app.bot.keyboards import wholesale_plans_keyboard
        plans = self.plans()
        self.assertEqual(wholesale_plans_keyboard(plans).inline_keyboard[0][0].callback_data, "shop:category:wholesale:1")
        self.assertEqual(wholesale_plans_keyboard(plans[:2], show_categories=False).inline_keyboard[0][0].callback_data, "shop:wholesale:plan:1")


class CategoryDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.session = self.sessions()
        self.user = BotUser(telegram_id=9001, username="buyer", referral_code="buyer")
        self.other = BotUser(telegram_id=9002, referral_code="other")
        self.session.add_all([self.user, self.other])
        await self.session.flush()
        self.platform = Plan(name="Platform", category="اصلی", price=100, pg_template_id=1, data_limit_gb=30)
        self.own = Plan(name="Shop", category="اقتصادی", price=200, pg_template_id=1, owner_reseller_id=self.user.id)
        self.foreign = Plan(name="Foreign", category="محرمانه", price=300, pg_template_id=1, owner_reseller_id=self.other.id)
        self.session.add_all([self.platform, self.own, self.foreign])
        await self.session.commit()

    async def asyncTearDown(self):
        await self.session.close()
        await self.engine.dispose()

    async def test_catalog_categories_are_shop_scoped(self):
        from app.services.plan_categories import category_names
        from app.services.plans_catalog import list_catalog_plans
        for staff, expected in [(OWNER, ["اصلی"]), ({"role": "reseller", "bot_user_id": self.user.id}, ["اقتصادی"]), ({"role": "pg_staff"}, [])]:
            self.assertEqual(category_names(await list_catalog_plans(self.session, staff)), expected)

    async def flags(self, *args, **kwargs):
        from app.services.orders import list_active_plans
        plans = await list_active_plans(self.session, include_trial=False, reseller_id=self.user.id)
        return {}, bool(plans), False, False, True, plans, plans, []

    async def test_category_callback_cannot_read_foreign_plan(self):
        from app.bot.handlers.shop import shop_category
        callback = SimpleNamespace(data=f"shop:category:fixed:{self.foreign.id}", answer=AsyncMock(), message=AsyncMock())
        with patch("app.bot.handlers.shop._answer_shop_maintenance", AsyncMock(return_value=False)), patch("app.bot.handlers.shop._shop_kind_flags", self.flags):
            await shop_category(callback, self.session, self.user)
        callback.answer.assert_awaited_once_with("دسته‌بندی در دسترس نیست.", show_alert=True)
        callback.message.edit_text.assert_not_awaited()

    async def test_category_callback_selects_only_matching_active_plans(self):
        from app.bot.handlers.shop import shop_category
        extra = Plan(name="Other", category="دیگر", price=100, owner_reseller_id=self.user.id)
        inactive = Plan(name="Hidden", category="اقتصادی", price=100, owner_reseller_id=self.user.id, is_active=False)
        self.session.add_all([extra, inactive])
        await self.session.commit()
        callback = SimpleNamespace(data=f"shop:category:fixed:{self.own.id}", answer=AsyncMock(), message=AsyncMock())
        with patch("app.bot.handlers.shop._answer_shop_maintenance", AsyncMock(return_value=False)), patch("app.bot.handlers.shop._shop_kind_flags", self.flags):
            await shop_category(callback, self.session, self.user)
        markup = callback.message.edit_text.call_args.kwargs["reply_markup"]
        self.assertEqual([row[0].callback_data for row in markup.inline_keyboard], [f"shop:plan:{self.own.id}", "shop:kind:fixed"])

    async def test_category_callback_rechecks_trial_and_wholesale_gates(self):
        from app.bot.handlers.shop import shop_category
        for kind in ("trial", "wholesale"):
            callback = SimpleNamespace(data=f"shop:category:{kind}:{self.own.id}", answer=AsyncMock(), message=AsyncMock())
            flags = ({}, True, False, False, False, [self.own], [self.own], [])
            with patch("app.bot.handlers.shop._answer_shop_maintenance", AsyncMock(return_value=False)), patch("app.bot.handlers.shop._shop_kind_flags", AsyncMock(return_value=flags)):
                await shop_category(callback, self.session, self.user)
            callback.message.edit_text.assert_not_awaited()

    async def test_reseller_category_save_rechecks_ownership(self):
        from app.bot.handlers.reseller_plans import res_plan_category_save
        message = SimpleNamespace(text="Hacked", answer=AsyncMock())
        state = SimpleNamespace(get_data=AsyncMock(return_value={"res_category_plan_id": self.foreign.id}), clear=AsyncMock())
        with patch("app.bot.handlers.reseller_plans._actor", AsyncMock(return_value=(self.user.id, SimpleNamespace()))), patch("app.bot.handlers.reseller_plans.has_bot_perm", return_value=True):
            await res_plan_category_save(message, self.session, self.user, state)
        self.assertEqual(self.foreign.category, "محرمانه")
        state.clear.assert_awaited_once()

    def endpoint(self, path, method):
        from app.api.app import create_api_app
        return next(r.endpoint for r in create_api_app().routes if getattr(r, "path", None) == path and method in (getattr(r, "methods", None) or set()))

    async def test_web_create_and_edit_persist_category(self):
        create = self.endpoint("/plans", "POST")
        edit = self.endpoint("/plans/{plan_id}/edit", "POST")
        staff = {"role": "reseller", "bot_user_id": self.user.id, "pg_access": {"allowed_template_ids": [1]}}
        request = SimpleNamespace(form=AsyncMock(return_value={"category": "  ویژه  "}))
        args = dict(request=request, name="New", price=100, duration_days=30, data_limit_gb="30", pg_template_id="1", description="", mode="template", staff=staff, session=self.session)
        with patch("app.services.pg_quota.assert_user_plan_within_limits", AsyncMock()):
            response = await create(**args, also_create_template="")
            self.assertEqual(response.status_code, 303)
            plan = (await self.session.execute(select(Plan).where(Plan.name == "New"))).scalar_one()
            self.assertEqual(plan.category, "ویژه")
            request.form.return_value = {"category": ""}
            await edit(plan_id=plan.id, sort_order=0, **args)
            self.assertIsNone(plan.category)
            request.form.return_value = {"category": "Hacked"}
            await edit(plan_id=self.foreign.id, sort_order=0, **args)
            self.assertEqual(self.foreign.category, "محرمانه")

    async def test_web_category_suggestions_and_filter_are_scoped(self):
        endpoint = self.endpoint("/plans", "GET")
        staff = {"role": "reseller", "bot_user_id": self.user.id}
        extra = Plan(name="Other", category="دیگر", price=100, owner_reseller_id=self.user.id)
        self.session.add(extra)
        await self.session.commit()
        request = SimpleNamespace(query_params={"category": "name:اقتصادی"})
        with patch("app.api.app.render", side_effect=lambda request, name, ctx: ctx), patch("app.services.plans_catalog.load_pg_plan_options", AsyncMock(return_value=([], [], None))), patch("app.services.plans_catalog.plan_limit_issue", AsyncMock(return_value=None)), patch("app.services.pg_quota.load_staff_limit_snapshot", AsyncMock(return_value={})), patch("app.services.pg_quota.limit_snapshot_cards", return_value=[]), patch("app.services.plans_catalog.custom_range_limit_issue", return_value=None):
            ctx = await endpoint(request=request, staff=staff, session=self.session)
        self.assertEqual(ctx["plan_categories"], ["اقتصادی", "دیگر"])
        self.assertEqual([p.id for p in ctx["plans"]], [self.own.id])

    async def test_deliver_order_sends_real_buyer_and_volume_to_pg(self):
        from app.services.orders import deliver_order
        self.platform.pg_username_pattern = "{username}_{plan_volume}{plan_unit}_{random}"
        order = Order(user_id=self.user.id, plan_id=self.platform.id, amount=100, status=OrderStatus.PAID.value)
        self.session.add(order)
        await self.session.commit()
        pg = SimpleNamespace(create_user_from_template=AsyncMock(return_value={"id": 123, "subscription_url": "https://example.com/sub/test"}))
        with patch("app.services.orders.get_pg", return_value=pg), patch("app.services.users.get_all_settings", AsyncMock(return_value={})), patch("app.services.orders._random_alnum", return_value="a1b2c3d4"):
            delivered = await deliver_order(self.session, order)
        self.assertEqual(delivered.status, OrderStatus.DELIVERED.value)
        self.assertEqual(pg.create_user_from_template.call_args.args[0]["username"], "buyer_30GB_a1b2c3d4")
        service = await self.session.get(UserService, delivered.service_id)
        self.assertEqual(service.pg_username, "buyer_30GB_a1b2c3d4")

    async def test_clone_preserves_category(self):
        from app.services.ux20 import clone_plan
        copy = await clone_plan(self.session, self.own.id, owner_reseller_id=self.user.id)
        self.assertEqual(copy.category, "اقتصادی")
        self.assertFalse(copy.is_active)
        self.assertEqual(copy.owner_reseller_id, self.user.id)

    async def test_bundle_export_import_preserves_category_and_old_bundles(self):
        from app.services.ux20 import export_shop_bundle, import_shop_bundle
        with patch("app.services.users.get_all_settings", AsyncMock(return_value={})):
            payload = await export_shop_bundle(self.session, reseller_id=self.user.id)
        self.assertEqual([p["category"] for p in payload["plans"]], ["اقتصادی"])
        with patch("app.services.ux20._validate_import_plan", AsyncMock()):
            await import_shop_bundle(self.session, payload, reseller_id=self.user.id, replace_plans=True)
            payload["plans"][0].pop("category")
            await import_shop_bundle(self.session, payload, reseller_id=self.other.id, replace_plans=True)
        own = (await self.session.execute(select(Plan).where(Plan.owner_reseller_id == self.user.id))).scalar_one()
        other = (await self.session.execute(select(Plan).where(Plan.owner_reseller_id == self.other.id))).scalar_one()
        self.assertEqual(own.category, "اقتصادی")
        self.assertIsNone(other.category)


class CategoryMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_plans_is_idempotent_and_downgrades(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        spec = importlib.util.spec_from_file_location("category_migration", ROOT / "alembic/versions/0031_plan_categories.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        engine = create_engine("sqlite:///:memory:")
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE TABLE plans (id INTEGER PRIMARY KEY, name VARCHAR(128))"))
                conn.execute(text("INSERT INTO plans VALUES (1, 'Existing')"))
                with Operations.context(MigrationContext.configure(conn)):
                    module.upgrade()
                    module.upgrade()
                    self.assertEqual(conn.execute(text("SELECT name, category FROM plans")).one(), ("Existing", None))
                    module.downgrade()
                self.assertNotIn("category", {c["name"] for c in inspect(conn).get_columns("plans")})
        finally:
            engine.dispose()
