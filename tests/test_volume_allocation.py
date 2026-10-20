"""Volume allocation gate for fixed-plan L1 shops (PR-A)."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.db.models import (
    BotUser,
    PgAdminSubscription,
    ResellerProfile,
    Role,
    UserService,
    WalletTransaction,
)
from app.services.billing import GB
from app.services.volume_allocation import (
    CUSTOMER_UNAVAILABLE_MSG,
    VolumeAllocationError,
    assert_volume_delta_allowed,
    build_allocation_snapshot,
    list_oversold_shop_ids,
    refund_volume_gate_once,
    reserve_creating_service,
    set_allow_volume_oversell,
    sum_allocated_bytes,
)

ROOT = Path(__file__).resolve().parents[1]


class VolumeHarness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self._tmp.name) / 'vol.db'}"
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self._tmp.cleanup()

    async def _shop(
        self,
        *,
        shop_id: int = 10,
        ceiling_gb: int = 10,
        allow_oversell: bool = False,
        payg: bool = False,
        extra_gb: int = 0,
    ) -> int:
        async with self.Session() as session:
            session.add(
                BotUser(
                    id=shop_id,
                    telegram_id=1000 + shop_id,
                    role=Role.RESELLER.value,
                    referral_code=f"s{shop_id}",
                )
            )
            session.add(
                ResellerProfile(
                    user_id=shop_id,
                    pg_admin_username=f"admin{shop_id}",
                    billing_mode="payg" if payg else "fixed",
                    allow_volume_oversell=allow_oversell,
                    is_active=True,
                )
            )
            if ceiling_gb > 0 or extra_gb > 0:
                session.add(
                    PgAdminSubscription(
                        pg_username=f"admin{shop_id}",
                        base_gb=ceiling_gb,
                        extra_gb_purchased=extra_gb,
                    )
                )
            await session.commit()
        return shop_id

    async def _service(
        self,
        shop_id: int,
        *,
        bytes_: int | None,
        cancelled: bool = False,
        expired: bool = False,
        synced: bool = True,
        bot_user_id: int | None = None,
    ) -> int:
        async with self.Session() as session:
            uid = bot_user_id or (9000 + shop_id)
            if await session.get(BotUser, uid) is None:
                session.add(
                    BotUser(
                        id=uid,
                        telegram_id=uid,
                        role=Role.USER.value,
                        referral_code=f"u{uid}",
                    )
                )
            now = datetime.now(timezone.utc)
            svc = UserService(
                bot_user_id=uid,
                pg_user_id=uid,
                pg_username=f"u-{uid}-{bytes_}",
                shop_id=shop_id,
                quota_data_limit_bytes=bytes_,
                quota_synced_at=now if synced else None,
                quota_expire_at=(now - timedelta(days=1)) if expired else (now + timedelta(days=7)),
                is_cancelled=cancelled,
                quota_status="active" if synced else None,
            )
            session.add(svc)
            await session.commit()
            return int(svc.id)


class GateBehaviourTests(VolumeHarness):
    async def test_switch_off_blocks_positive_delta(self) -> None:
        shop = await self._shop(ceiling_gb=5, allow_oversell=False)
        await self._service(shop, bytes_=4 * GB)
        async with self.Session() as session:
            with self.assertRaises(VolumeAllocationError) as ctx:
                await assert_volume_delta_allowed(
                    session, shop_id=shop, delta_bytes=2 * GB, audience="admin"
                )
            self.assertIn("سقف حجم پر است", ctx.exception.message)
            self.assertIn("از", ctx.exception.message)

    async def test_switch_on_allows_oversell(self) -> None:
        shop = await self._shop(ceiling_gb=5, allow_oversell=True)
        await self._service(shop, bytes_=4 * GB)
        async with self.Session() as session:
            await assert_volume_delta_allowed(
                session, shop_id=shop, delta_bytes=10 * GB, audience="admin"
            )

    async def test_customer_message_hides_budget(self) -> None:
        shop = await self._shop(ceiling_gb=1, allow_oversell=False)
        await self._service(shop, bytes_=1 * GB)
        async with self.Session() as session:
            with self.assertRaises(VolumeAllocationError) as ctx:
                await assert_volume_delta_allowed(
                    session, shop_id=shop, delta_bytes=1 * GB, audience="customer"
                )
            self.assertEqual(ctx.exception.user_message(), CUSTOMER_UNAVAILABLE_MSG)
            self.assertNotIn("گیگ", ctx.exception.user_message())

    async def test_negative_and_zero_delta_free(self) -> None:
        shop = await self._shop(ceiling_gb=1, allow_oversell=False)
        await self._service(shop, bytes_=1 * GB)
        async with self.Session() as session:
            await assert_volume_delta_allowed(
                session, shop_id=shop, delta_bytes=-GB, audience="admin"
            )
            # zero with allow_unlimited True is a no-op shrink path
            await assert_volume_delta_allowed(
                session,
                shop_id=shop,
                delta_bytes=0,
                audience="admin",
                allow_unlimited=True,
            )

    async def test_unlimited_create_rejected_when_gated(self) -> None:
        shop = await self._shop(ceiling_gb=10, allow_oversell=False)
        async with self.Session() as session:
            with self.assertRaises(VolumeAllocationError):
                await assert_volume_delta_allowed(
                    session, shop_id=shop, delta_bytes=0, audience="admin"
                )

    async def test_expired_counts_until_cancelled(self) -> None:
        shop = await self._shop(ceiling_gb=5, allow_oversell=False)
        await self._service(shop, bytes_=3 * GB, expired=True)
        async with self.Session() as session:
            self.assertEqual(await sum_allocated_bytes(session, shop), 3 * GB)
            with self.assertRaises(VolumeAllocationError):
                await assert_volume_delta_allowed(
                    session, shop_id=shop, delta_bytes=3 * GB, audience="admin"
                )

    async def test_cancel_frees_allocation(self) -> None:
        shop = await self._shop(ceiling_gb=5, allow_oversell=False)
        await self._service(shop, bytes_=5 * GB, cancelled=True)
        async with self.Session() as session:
            self.assertEqual(await sum_allocated_bytes(session, shop), 0)
            await assert_volume_delta_allowed(
                session, shop_id=shop, delta_bytes=5 * GB, audience="admin"
            )

    async def test_unlimited_and_unsynced_count_zero_and_listed(self) -> None:
        shop = await self._shop(ceiling_gb=5, allow_oversell=False)
        await self._service(shop, bytes_=0, synced=True)
        await self._service(shop, bytes_=None, synced=False, bot_user_id=9001)
        async with self.Session() as session:
            self.assertEqual(await sum_allocated_bytes(session, shop), 0)
            snap = await build_allocation_snapshot(session, shop)
            self.assertIsNotNone(snap)
            kinds = {row["kind"] for row in snap.unlimited_services}
            self.assertEqual(kinds, {"unlimited", "unsynced"})

    async def test_oversold_blocks_increase_allows_decrease(self) -> None:
        shop = await self._shop(ceiling_gb=5, allow_oversell=False)
        await self._service(shop, bytes_=8 * GB)  # already oversold
        async with self.Session() as session:
            with self.assertRaises(VolumeAllocationError):
                await assert_volume_delta_allowed(
                    session, shop_id=shop, delta_bytes=GB, audience="admin"
                )
            await assert_volume_delta_allowed(
                session, shop_id=shop, delta_bytes=-GB, audience="admin"
            )
            snap = await build_allocation_snapshot(session, shop)
            self.assertTrue(snap.is_oversold)

    async def test_payg_exempt(self) -> None:
        shop = await self._shop(ceiling_gb=1, allow_oversell=False, payg=True)
        await self._service(shop, bytes_=10 * GB)
        async with self.Session() as session:
            await assert_volume_delta_allowed(
                session, shop_id=shop, delta_bytes=10 * GB, audience="admin"
            )

    async def test_unknown_ceiling_fail_closed(self) -> None:
        shop = await self._shop(ceiling_gb=0, allow_oversell=False)
        async with self.Session() as session:
            # No subscription row / zero ceiling → unknown
            with self.assertRaises(VolumeAllocationError):
                await assert_volume_delta_allowed(
                    session, shop_id=shop, delta_bytes=GB, audience="admin"
                )

    async def test_tenancy_other_shop_not_counted(self) -> None:
        a = await self._shop(shop_id=10, ceiling_gb=5, allow_oversell=False)
        b = await self._shop(shop_id=20, ceiling_gb=5, allow_oversell=False)
        await self._service(a, bytes_=5 * GB)
        await self._service(b, bytes_=1 * GB, bot_user_id=9200)
        async with self.Session() as session:
            self.assertEqual(await sum_allocated_bytes(session, a), 5 * GB)
            self.assertEqual(await sum_allocated_bytes(session, b), 1 * GB)
            await assert_volume_delta_allowed(
                session, shop_id=b, delta_bytes=3 * GB, audience="admin"
            )

    async def test_reseller_cannot_enable_oversell(self) -> None:
        await self._shop(shop_id=10, ceiling_gb=5, allow_oversell=False)
        async with self.Session() as session:
            profile = await session.scalar(
                select(ResellerProfile).where(ResellerProfile.user_id == 10)
            )
            with self.assertRaises(VolumeAllocationError):
                await set_allow_volume_oversell(
                    session, profile, allow=True, actor_is_owner=False
                )
            await set_allow_volume_oversell(
                session, profile, allow=True, actor_is_owner=True
            )
            self.assertTrue(profile.allow_volume_oversell)


class PathGateTests(VolumeHarness):
    async def test_loyalty_traffic_rejected_when_full(self) -> None:
        from app.services.loyalty import apply_service_reward

        shop = await self._shop(ceiling_gb=2, allow_oversell=False)
        svc_id = await self._service(shop, bytes_=2 * GB)
        async with self.Session() as session:
            service = await session.get(UserService, svc_id)
            user = await session.get(BotUser, service.bot_user_id)
            with (
                patch(
                    "app.services.service_cancellations.lock_service_mutation",
                    new=AsyncMock(),
                ),
                patch(
                    "app.services.service_scope.service_shop_id",
                    new=AsyncMock(return_value=shop),
                ),
                patch(
                    "app.services.users.current_shop_reseller_id",
                    return_value=shop,
                ),
                patch(
                    "app.services.pasarguard.get_pg_for_reseller",
                    new=AsyncMock(
                        return_value=SimpleNamespace(
                            get_user_by_id=AsyncMock(
                                return_value={"data_limit": 2 * GB, "status": "active"}
                            ),
                            modify_user_by_id=AsyncMock(),
                        )
                    ),
                ),
            ):
                with self.assertRaises(ValueError) as ctx:
                    await apply_service_reward(
                        session, user, service, "traffic_gb", 1
                    )
            self.assertEqual(str(ctx.exception), CUSTOMER_UNAVAILABLE_MSG)

    async def test_addon_volume_rejected_when_full(self) -> None:
        from app.services.service_addons import KIND_VOLUME, _apply_pack_to_service

        shop = await self._shop(ceiling_gb=2, allow_oversell=False)
        svc_id = await self._service(shop, bytes_=2 * GB)
        async with self.Session() as session:
            service = await session.get(UserService, svc_id)
            with patch(
                "app.services.pasarguard.get_pg_for_reseller",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        get_user_by_id=AsyncMock(
                            return_value={"data_limit": 2 * GB, "status": "active"}
                        ),
                        modify_user_by_id=AsyncMock(),
                    )
                ),
            ):
                with self.assertRaises(ValueError) as ctx:
                    await _apply_pack_to_service(
                        session,
                        service,
                        kind=KIND_VOLUME,
                        amount=1.0,
                        order_reseller_id=shop,
                    )
            self.assertEqual(str(ctx.exception), CUSTOMER_UNAVAILABLE_MSG)

    async def test_buy_extra_gb_raises_ceiling_not_allocation(self) -> None:
        """buy_extra_gb increases the subscription ceiling; allocation gate does not block it."""
        from app.services.reseller_capacity import buy_extra_gb

        shop = await self._shop(ceiling_gb=2, allow_oversell=False, extra_gb=0)
        await self._service(shop, bytes_=2 * GB)
        async with self.Session() as session:
            user = await session.get(BotUser, shop)
            user.wallet_balance = 1_000_000
            profile = await session.scalar(
                select(ResellerProfile).where(ResellerProfile.user_id == shop)
            )
            plan = SimpleNamespace(
                allow_buy_extra=True,
                billing_mode="fixed",
                plan_kind="subscription",
                extra_gb_price=1000,
            )
            pg = AsyncMock()
            pg.get_admin = AsyncMock(return_value={"data_limit": 2 * GB})
            pg.modify_admin = AsyncMock()
            with (
                patch("app.services.reseller_capacity.plan_allows_buy_extra", return_value=True),
                patch("app.services.reseller_capacity.is_payg", return_value=False),
                patch("app.services.pasarguard.get_pg", return_value=pg),
                patch(
                    "app.services.pg_admin_subscription.record_unit_extra",
                    new=AsyncMock(),
                ),
            ):
                await buy_extra_gb(
                    session, user=user, profile=profile, plan=plan, gb=1
                )
            pg.modify_admin.assert_awaited()


class ConcurrencyAndRefundTests(VolumeHarness):
    async def test_second_reservation_fails_after_first_commits(self) -> None:
        shop = await self._shop(ceiling_gb=5, allow_oversell=False)
        async with self.Session() as session:
            session.add(
                BotUser(id=1, telegram_id=1, role=Role.USER.value, referral_code="u1")
            )
            await session.flush()
            await assert_volume_delta_allowed(
                session, shop_id=shop, delta_bytes=5 * GB, audience="admin"
            )
            await reserve_creating_service(
                session,
                bot_user_id=1,
                shop_id=shop,
                plan_id=None,
                pg_username="pending-a",
                data_limit_bytes=5 * GB,
                remark="order:1",
            )
            await session.commit()
        async with self.Session() as session:
            with self.assertRaises(VolumeAllocationError):
                await assert_volume_delta_allowed(
                    session, shop_id=shop, delta_bytes=1 * GB, audience="admin"
                )

    async def test_unknown_panel_keeps_reservation(self) -> None:
        from app.services.volume_allocation import (
            mark_service_review,
            QUOTA_STATUS_REVIEW,
        )

        shop = await self._shop(ceiling_gb=10, allow_oversell=False)
        async with self.Session() as session:
            session.add(
                BotUser(id=1, telegram_id=1, role=Role.USER.value, referral_code="u1b")
            )
            svc = await reserve_creating_service(
                session,
                bot_user_id=1,
                shop_id=shop,
                plan_id=None,
                pg_username="pending-b",
                data_limit_bytes=3 * GB,
                remark="order:2",
            )
            await mark_service_review(session, svc)
            await session.commit()
            self.assertEqual(svc.quota_status, QUOTA_STATUS_REVIEW)
            self.assertEqual(await sum_allocated_bytes(session, shop), 3 * GB)

    async def test_delivery_refund_exactly_once(self) -> None:
        shop = await self._shop(ceiling_gb=1, allow_oversell=False)
        async with self.Session() as session:
            user = await session.get(BotUser, shop)
            user.wallet_balance = 0
            await session.commit()
        async with self.Session() as session:
            user = await session.get(BotUser, shop)
            first = await refund_volume_gate_once(
                session, user=user, amount=5000, order_id=42, shop_id=None
            )
            await session.commit()
            second = await refund_volume_gate_once(
                session, user=user, amount=5000, order_id=42, shop_id=None
            )
            await session.commit()
            self.assertTrue(first)
            self.assertFalse(second)
            await session.refresh(user)
            self.assertEqual(int(user.wallet_balance), 5000)
            reasons = (
                await session.execute(
                    select(WalletTransaction.reason).where(
                        WalletTransaction.user_id == shop
                    )
                )
            ).scalars().all()
            self.assertEqual(reasons, ["volume_gate_refund:order:42"])


class OversoldListAndMigrationTests(VolumeHarness):
    async def test_owner_oversold_list(self) -> None:
        a = await self._shop(shop_id=10, ceiling_gb=5, allow_oversell=False)
        b = await self._shop(shop_id=20, ceiling_gb=5, allow_oversell=False)
        await self._service(a, bytes_=8 * GB)
        await self._service(b, bytes_=1 * GB, bot_user_id=9200)
        async with self.Session() as session:
            oversold = await list_oversold_shop_ids(session)
            self.assertEqual(oversold, [a])

    def test_migration_upgrade_twice_and_downgrade(self) -> None:
        import sqlalchemy as sa
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        spec = importlib.util.spec_from_file_location(
            "vol_mig", ROOT / "alembic/versions/0065_allow_volume_oversell.py"
        )
        migration = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(migration)
        engine = sa.create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE reseller_profiles ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)"
                )
            )
            conn.execute(text("INSERT INTO reseller_profiles VALUES (1, 10)"))
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
                migration.upgrade()
                row = conn.execute(
                    text("SELECT allow_volume_oversell FROM reseller_profiles")
                ).one()
                self.assertEqual(int(row[0]), 1)
                migration.downgrade()
                cols = {c["name"] for c in sa.inspect(conn).get_columns("reseller_profiles")}
                self.assertNotIn("allow_volume_oversell", cols)
                self.assertEqual(
                    conn.execute(text("SELECT user_id FROM reseller_profiles")).scalar(),
                    10,
                )
                migration.upgrade()
                self.assertIn(
                    "allow_volume_oversell",
                    {c["name"] for c in sa.inspect(conn).get_columns("reseller_profiles")},
                )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
