"""Manual bot-user create + plan assign from web panel."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select


class AdminCreateBotUserTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_invalid_telegram_id(self):
        from app.services.bot_user_admin import admin_create_bot_user

        session = AsyncMock()
        with self.assertRaises(ValueError):
            await admin_create_bot_user(session, telegram_id=0)
        with self.assertRaises(ValueError):
            await admin_create_bot_user(session, telegram_id=-5)

    async def test_rejects_duplicate(self):
        from app.services.bot_user_admin import admin_create_bot_user

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = MagicMock(id=1)
        session.execute = AsyncMock(return_value=result)
        with self.assertRaisesRegex(ValueError, "قبلاً"):
            await admin_create_bot_user(session, telegram_id=123456789)

    async def test_creates_platform_user(self):
        from app.db.models import BotUser, Role
        from app.services.bot_user_admin import admin_create_bot_user

        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda u: u)
        session.add = MagicMock()

        user = await admin_create_bot_user(
            session,
            telegram_id=987654321,
            username="@alice",
            full_name="Alice",
            reseller_id=None,
        )
        self.assertEqual(user.telegram_id, 987654321)
        self.assertEqual(user.username, "alice")
        self.assertEqual(user.full_name, "Alice")
        self.assertEqual(user.role, Role.USER.value)
        self.assertIsNone(user.reseller_id)
        session.add.assert_called_once()
        added = session.add.call_args.args[0]
        self.assertIsInstance(added, BotUser)


class AdminProvisionServiceTests(unittest.IsolatedAsyncioTestCase):
    def _user(self, *, reseller_id=None):
        return SimpleNamespace(id=10, reseller_id=reseller_id)

    def _plan(self, **kw):
        defaults = dict(
            id=5,
            is_active=True,
            is_trial=False,
            owner_reseller_id=None,
            data_limit_gb=10.0,
            duration_days=30,
            pg_template_id=None,
            pg_group_ids="1",
            name="Test Plan",
        )
        defaults.update(kw)
        return SimpleNamespace(**defaults)

    async def test_rejects_trial_plan(self):
        from app.services.bot_user_admin import admin_provision_service

        with self.assertRaisesRegex(ValueError, "تست"):
            await admin_provision_service(
                AsyncMock(),
                self._user(),
                self._plan(is_trial=True),
            )

    async def test_rejects_shop_mismatch(self):
        from app.services.bot_user_admin import admin_provision_service

        user = self._user(reseller_id=7)
        plan = self._plan(owner_reseller_id=None)
        with self.assertRaisesRegex(ValueError, "فروشگاه"):
            await admin_provision_service(AsyncMock(), user, plan)

    async def test_rejects_staff_plan_access(self):
        from app.services.bot_user_admin import admin_provision_service

        staff = {"role": "admin", "principal_id": 1}
        user = self._user()
        plan = self._plan(owner_reseller_id=99)
        with self.assertRaisesRegex(ValueError, "فروشگاه"):
            await admin_provision_service(
                AsyncMock(), user, plan, staff=staff
            )

    async def test_provisions_platform_user(self):
        from app.services.bot_user_admin import admin_provision_service

        user = self._user()
        plan = self._plan()
        pg_user = {
            "id": 42,
            "username": "clk_abcd",
            "subscription_url": "https://sub.example/x",
        }
        pg = AsyncMock()
        pg.create_user = AsyncMock(return_value=pg_user)
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda s: s)
        session.add = MagicMock()
        session.rollback = AsyncMock()

        with patch("app.services.pasarguard.get_pg", return_value=pg), patch(
            "app.services.orders.generate_pg_username",
            AsyncMock(return_value="clk_abcd"),
        ), patch(
            "app.services.orders._reseller_pg_link",
            AsyncMock(return_value=(None, None)),
        ):
            svc = await admin_provision_service(
                session, user, plan, staff=None, actor="owner"
            )
        self.assertEqual(svc.pg_user_id, 42)
        self.assertEqual(svc.plan_id, 5)
        self.assertEqual(svc.bot_user_id, 10)
        pg.create_user.assert_awaited()


class ManualUserProvisionUiTests(unittest.TestCase):
    def test_routes_and_templates(self):
        pages = Path("app/api/user_pages.py").read_text(encoding="utf-8")
        self.assertIn("/users/create", pages)
        self.assertIn("/users/{user_id}/services", pages)
        self.assertIn("list_catalog_plans", pages)
        self.assertIn("get_owned_plan", pages)

        users = Path("app/web/templates/users.html").read_text(encoding="utf-8")
        self.assertIn("modal-user-create", users)
        self.assertIn("/users/create", users)

        edit = Path("app/web/templates/_user_edit_body.html").read_text(encoding="utf-8")
        self.assertIn("اختصاص پلن جدید", edit)
        self.assertIn("/users/{{ user.id }}/services", edit)

    def test_create_route_uses_scope(self):
        src = Path("app/api/user_pages.py").read_text(encoding="utf-8")
        fn = src.split("async def user_create", 1)[1].split("\n    @app.", 1)[0]
        self.assertIn("resolve_shop_scope_id", fn)
        self.assertIn("admin_create_bot_user", fn)
        self.assertIn("require_admin", src.split("async def user_create")[0])

    def test_provision_route_checks_scope(self):
        src = Path("app/api/user_pages.py").read_text(encoding="utf-8")
        fn = src.split("async def user_provision_service", 1)[1].split(
            "\n    @app.", 1
        )[0]
        self.assertIn("_require_scoped_user", fn)
        self.assertIn("get_owned_plan", fn)
        self.assertIn("admin_provision_service", fn)


if __name__ == "__main__":
    unittest.main()
