"""External (panel-only) volume allocation sync (PR-B)."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.db.models import BotUser, PgAdminSubscription, ResellerProfile, Role, UserService
from app.services.billing import GB
from app.services.volume_allocation import assert_volume_delta_allowed, sum_allocated_bytes
from app.services.volume_allocation_external import (
    compute_external_bytes,
    external_sync_is_stale,
    list_panel_users_for_admin,
    run_external_allocation_sync,
    sync_shop_external_allocation,
)

ROOT = Path(__file__).resolve().parents[1]


class ExternalHarness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self._tmp.name) / 'ext.db'}"
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self._tmp.cleanup()

    async def _shop(self, shop_id: int = 10, *, ceiling_gb: int = 10) -> ResellerProfile:
        async with self.Session() as session:
            session.add(
                BotUser(
                    id=shop_id,
                    telegram_id=1000 + shop_id,
                    role=Role.RESELLER.value,
                    referral_code=f"s{shop_id}",
                )
            )
            profile = ResellerProfile(
                user_id=shop_id,
                pg_admin_username=f"admin{shop_id}",
                billing_mode="fixed",
                allow_volume_oversell=False,
                is_active=True,
                external_allocated_bytes=0,
            )
            session.add(profile)
            session.add(
                PgAdminSubscription(
                    pg_username=f"admin{shop_id}",
                    base_gb=ceiling_gb,
                    extra_gb_purchased=0,
                )
            )
            await session.commit()
            await session.refresh(profile)
            return profile


class PaginationAndMatchTests(ExternalHarness):
    async def test_pagination_collects_all_pages(self) -> None:
        pages = {
            0: {
                "users": [
                    {"id": 1, "username": "a", "data_limit": GB},
                    {"id": 2, "username": "b", "data_limit": 2 * GB},
                ]
            },
            2: {
                "users": [
                    {"id": 3, "username": "c", "data_limit": 3 * GB},
                ]
            },
        }

        async def get_users(*, admin, limit, offset):
            return pages.get(offset, {"users": []})

        pg = AsyncMock()
        pg.get_users = get_users
        users = await list_panel_users_for_admin(pg, "admin10", page_size=2)
        self.assertEqual(len(users), 3)

    async def test_panel_only_users_count_as_external(self) -> None:
        await self._shop()
        async with self.Session() as session:
            session.add(
                BotUser(id=1, telegram_id=1, role=Role.USER.value, referral_code="u1")
            )
            session.add(
                UserService(
                    bot_user_id=1,
                    pg_user_id=1,
                    pg_username="local-one",
                    shop_id=10,
                    quota_data_limit_bytes=GB,
                    quota_synced_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            panel = [
                {"id": 1, "username": "local-one", "data_limit": GB},
                {"id": 99, "username": "panel-only", "data_limit": 4 * GB},
                {"id": 100, "username": "unlimited", "data_limit": 0},
            ]
            external, unmatched = await compute_external_bytes(
                session, shop_id=10, panel_users=panel
            )
            self.assertEqual(unmatched, 2)
            self.assertEqual(external, 4 * GB)


class SyncBehaviourTests(ExternalHarness):
    async def test_sync_stores_external_and_blocks_sell(self) -> None:
        profile = await self._shop(ceiling_gb=5)
        pg = AsyncMock()
        pg.get_users = AsyncMock(
            return_value={
                "users": [
                    {"id": 50, "username": "panel-x", "data_limit": 5 * GB},
                ]
            }
        )
        pg.get_admin = AsyncMock(return_value={"data_limit": 5 * GB})
        async with self.Session() as session:
            row = await session.get(ResellerProfile, profile.id)
            result = await sync_shop_external_allocation(session, row, pg=pg)
            await session.commit()
            self.assertEqual(result.external_bytes, 5 * GB)
            self.assertFalse(result.stale)
            self.assertEqual(await sum_allocated_bytes(session, 10), 5 * GB)
            with self.assertRaises(Exception):
                await assert_volume_delta_allowed(
                    session, shop_id=10, delta_bytes=GB, audience="admin"
                )

    async def test_panel_outage_keeps_previous_and_does_not_open_sell(self) -> None:
        profile = await self._shop(ceiling_gb=5)
        async with self.Session() as session:
            row = await session.get(ResellerProfile, profile.id)
            row.external_allocated_bytes = 5 * GB
            row.external_alloc_synced_at = datetime.now(timezone.utc) - timedelta(hours=2)
            await session.commit()
        pg = AsyncMock()
        pg.get_users = AsyncMock(side_effect=TimeoutError("panel down"))
        async with self.Session() as session:
            row = await session.get(ResellerProfile, profile.id)
            result = await sync_shop_external_allocation(session, row, pg=pg)
            self.assertTrue(result.stale)
            self.assertEqual(result.external_bytes, 5 * GB)
            self.assertEqual(int(row.external_allocated_bytes), 5 * GB)
            with self.assertRaises(Exception):
                await assert_volume_delta_allowed(
                    session, shop_id=10, delta_bytes=GB, audience="admin"
                )

    async def test_one_bad_shop_does_not_stop_others(self) -> None:
        await self._shop(shop_id=10, ceiling_gb=10)
        await self._shop(shop_id=20, ceiling_gb=10)

        async def factory(session, shop_id):
            pg = AsyncMock()
            if shop_id == 10:
                pg.get_users = AsyncMock(side_effect=RuntimeError("boom"))
            else:
                pg.get_users = AsyncMock(
                    return_value={
                        "users": [{"id": 7, "username": "ok", "data_limit": 2 * GB}]
                    }
                )
                pg.get_admin = AsyncMock(return_value={"data_limit": 10 * GB})
            return pg

        async with self.Session() as session:
            results = await run_external_allocation_sync(
                session, concurrency=2, pg_factory=factory
            )
            by_shop = {r.shop_id: r for r in results}
            self.assertTrue(by_shop[10].stale)
            self.assertEqual(by_shop[20].external_bytes, 2 * GB)
            self.assertFalse(by_shop[20].stale)

    def test_stale_after_two_periods(self) -> None:
        now = datetime.now(timezone.utc)
        self.assertTrue(
            external_sync_is_stale(now - timedelta(minutes=31), period_minutes=15, now=now)
        )
        self.assertFalse(
            external_sync_is_stale(now - timedelta(minutes=20), period_minutes=15, now=now)
        )


class MigrationTests(unittest.TestCase):
    def test_migration_upgrade_twice_and_downgrade(self) -> None:
        import sqlalchemy as sa
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        spec = importlib.util.spec_from_file_location(
            "ext_mig", ROOT / "alembic/versions/0066_external_volume_allocation.py"
        )
        migration = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(migration)
        engine = sa.create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE reseller_profiles ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                    "allow_volume_oversell BOOLEAN NOT NULL DEFAULT 1)"
                )
            )
            conn.execute(text("INSERT INTO reseller_profiles VALUES (1, 10, 1)"))
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
                migration.upgrade()
                row = conn.execute(
                    text(
                        "SELECT external_allocated_bytes, external_alloc_synced_at "
                        "FROM reseller_profiles"
                    )
                ).one()
                self.assertEqual(int(row[0]), 0)
                self.assertIsNone(row[1])
                migration.downgrade()
                cols = {c["name"] for c in sa.inspect(conn).get_columns("reseller_profiles")}
                self.assertNotIn("external_allocated_bytes", cols)
                migration.upgrade()
                cols = {c["name"] for c in sa.inspect(conn).get_columns("reseller_profiles")}
                self.assertIn("external_allocated_bytes", cols)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
