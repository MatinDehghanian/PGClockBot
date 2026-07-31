"""Critical: resellers/pg_staff must never keep users under the panel owner.

PasarGuard enforces role quotas only for the authenticated admin. This panel
always calls the API as sudo/owner then reassigns ownership — so any path that
skips set_owner (or skips quota when PG link is missing) is a bypass.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import OrderStatus
from app.services.pg_quota import PgQuotaError, assert_can_create_user, assert_reseller_can_deliver


class FailClosedWithoutPgLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_user_fails_without_pg_username(self):
        with self.assertRaises(PgQuotaError) as ctx:
            await assert_can_create_user(
                {"role": "reseller"},
                data_limit=1024**3,
                expire_ts=None,
            )
        self.assertIn("تنظیم نشده", ctx.exception.message)

    async def test_pg_staff_create_fails_without_pg_username(self):
        with self.assertRaises(PgQuotaError):
            await assert_can_create_user(
                {"role": "pg_staff", "pg_admin_username": "  "},
                from_template=True,
            )

    async def test_reseller_deliver_fails_without_pg_link(self):
        with self.assertRaises(PgQuotaError) as ctx:
            await assert_reseller_can_deliver(pg_admin_username=None)
        self.assertIn("تحویل", ctx.exception.message)


class DeliverOrderOwnerAssignTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_owner_failure_deletes_pg_user(self):
        from app.services.orders import deliver_order

        plan = SimpleNamespace(
            id=1,
            data_limit_gb=10,
            duration_days=30,
            pg_template_id=5,
            pg_group_ids=None,
        )
        order = SimpleNamespace(
            id=99,
            status=OrderStatus.PAID.value,
            service_id=None,
            user_id=7,
            reseller_id=42,
            amount=1000,
            discount_code=None,
            plan=plan,
            user=None,
        )

        pg = AsyncMock()
        pg.create_user_from_template = AsyncMock(
            return_value={"id": 555, "username": "clk_x", "subscription_url": "https://x/sub"}
        )
        pg.set_owner_by_id = AsyncMock(side_effect=RuntimeError("owner denied"))
        pg.delete_user_by_id = AsyncMock()

        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                # with_for_update order load
                MagicMock(scalar_one=MagicMock(return_value=order)),
                # ResellerProfile lookup
                MagicMock(scalar_one_or_none=MagicMock(return_value=SimpleNamespace(
                    pg_admin_username="res_admin",
                    commission_percent=10,
                    balance=0,
                    user_id=42,
                ))),
            ]
        )

        with (
            patch("app.services.orders.get_pg", return_value=pg),
            patch("app.services.orders.generate_pg_username", new=AsyncMock(return_value="clk_x")),
            patch(
                "app.services.orders._reseller_pg_link",
                new=AsyncMock(return_value=("res_admin", 3)),
            ),
            patch(
                "app.services.orders.assert_reseller_can_deliver",
                new=AsyncMock(),
            ),
        ):
            with self.assertRaises(ValueError) as ctx:
                await deliver_order(session, order)

        self.assertIn("مالکیت", str(ctx.exception))
        pg.set_owner_by_id.assert_awaited_once_with(555, "res_admin")
        pg.delete_user_by_id.assert_awaited_once_with(555)
        session.commit.assert_not_awaited()

    async def test_success_assigns_owner_before_commit(self):
        from app.services.orders import deliver_order

        plan = SimpleNamespace(
            id=1,
            data_limit_gb=10,
            duration_days=30,
            pg_template_id=5,
            pg_group_ids=None,
        )
        order = SimpleNamespace(
            id=99,
            status=OrderStatus.PAID.value,
            service_id=None,
            user_id=7,
            reseller_id=42,
            amount=1000,
            discount_code=None,
            plan=plan,
            user=None,
        )
        profile = SimpleNamespace(
            pg_admin_username="res_admin",
            commission_percent=10,
            balance=0,
            user_id=42,
        )

        pg = AsyncMock()
        pg.create_user_from_template = AsyncMock(
            return_value={"id": 555, "username": "clk_x", "subscription_url": "https://x/sub"}
        )
        pg.set_owner_by_id = AsyncMock(return_value={})
        pg.delete_user_by_id = AsyncMock()

        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one=MagicMock(return_value=order)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=profile)),
            ]
        )

        with (
            patch("app.services.orders.get_pg", return_value=pg),
            patch("app.services.orders.generate_pg_username", new=AsyncMock(return_value="clk_x")),
            patch(
                "app.services.orders._reseller_pg_link",
                new=AsyncMock(return_value=("res_admin", 3)),
            ),
            patch(
                "app.services.orders.assert_reseller_can_deliver",
                new=AsyncMock(),
            ),
            patch(
                "app.services.orders.UserService",
                side_effect=lambda **kw: SimpleNamespace(id=1, **kw),
            ),
            patch("app.services.orders.extract_sub_token", return_value="tok"),
        ):
            result = await deliver_order(session, order)

        pg.set_owner_by_id.assert_awaited_once_with(555, "res_admin")
        pg.delete_user_by_id.assert_not_awaited()
        self.assertEqual(result.status, OrderStatus.DELIVERED.value)
        self.assertEqual(profile.balance, 100)  # 10% of 1000


class SourceWiringGuards(unittest.TestCase):
    def test_orders_no_longer_swallows_set_owner(self):
        src = Path("app/services/orders.py").read_text(encoding="utf-8")
        # Old bypass: set_owner failure was ignored with bare pass
        self.assertNotIn("await pg.set_owner_by_id(service.pg_user_id, profile.pg_admin_username)\n            except Exception:\n                pass", src)
        self.assertIn("مالکیت ست نشد و حذف شد", src)
        self.assertIn("delete_user_by_id", src)
        # Reseller path must always call quota assert (not only when pg_owner truthy)
        self.assertIn("if order.reseller_id:", src)
        self.assertIn("assert_reseller_can_deliver", src)

    def test_web_create_requires_pg_owner(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn("ادمین پاسارگارد برای این حساب تنظیم نشده است", src)
        # hosts + nodes mutations gated for limited admins
        hosts_idx = src.find("async def pg_hosts_create")
        nodes_idx = src.find("async def pg_node_reconnect")
        self.assertGreater(hosts_idx, 0)
        self.assertGreater(nodes_idx, 0)
        self.assertIn("assert_can_mutate_owned_users", src[hosts_idx : hosts_idx + 800])
        self.assertIn("assert_can_mutate_owned_users", src[nodes_idx : nodes_idx + 500])

    def test_bot_pg_users_still_platform_admin_only(self):
        src = Path("app/bot/handlers/admin_pg_users.py").read_text(encoding="utf-8")
        self.assertIn("is_platform_admin as _is_admin", src)
        self.assertIn("if not _is_admin(db_user):", src)


if __name__ == "__main__":
    unittest.main()
