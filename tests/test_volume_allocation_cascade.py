"""Cascading L1→L2 volume budgets (PR-C)."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.db.models import (
    BotUser,
    OrgPrincipal,
    OrgPrincipalProvision,
    PgAdminSubscription,
    ResellerProfile,
    Role,
    UserService,
)
from app.services.billing import GB
from app.services.org_principals import DEPTH_ONE, DEPTH_TWO, STATUS_ACTIVE
from app.services.volume_allocation import assert_volume_delta_allowed
from app.services.volume_allocation_cascade import (
    CascadeBudgetError,
    assert_l2_extra_gb_against_parent,
    set_child_volume_ceiling,
    sum_children_ceiling_bytes,
)

ROOT = Path(__file__).resolve().parents[1]


class CascadeHarness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self._tmp.name) / 'casc.db'}"
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self._tmp.cleanup()

    async def _tree(
        self,
        *,
        parent_ceiling_gb: int = 100,
        child_ceiling_gb: int | None = 40,
    ) -> tuple[int, int, int, int]:
        """Return (parent_shop, child_shop, parent_principal_id, child_principal_id)."""
        async with self.Session() as session:
            session.add(
                BotUser(id=10, telegram_id=10, role=Role.RESELLER.value, referral_code="p")
            )
            session.add(
                BotUser(id=20, telegram_id=20, role=Role.RESELLER.value, referral_code="c")
            )
            parent_prof = ResellerProfile(
                user_id=10,
                pg_admin_username="parent-admin",
                billing_mode="fixed",
                allow_volume_oversell=False,
                is_active=True,
            )
            child_prof = ResellerProfile(
                user_id=20,
                pg_admin_username="child-admin",
                billing_mode="fixed",
                allow_volume_oversell=False,
                is_active=True,
            )
            session.add(parent_prof)
            session.add(child_prof)
            await session.flush()
            session.add(
                PgAdminSubscription(
                    pg_username="parent-admin",
                    base_gb=parent_ceiling_gb,
                    extra_gb_purchased=0,
                )
            )
            if child_ceiling_gb:
                session.add(
                    PgAdminSubscription(
                        pg_username="child-admin",
                        base_gb=child_ceiling_gb,
                        extra_gb_purchased=0,
                    )
                )
            parent = OrgPrincipal(
                parent_id=None,
                depth=DEPTH_ONE,
                status=STATUS_ACTIVE,
                pg_username="parent-admin",
                reseller_profile_id=int(parent_prof.id),
            )
            session.add(parent)
            await session.flush()
            child = OrgPrincipal(
                parent_id=int(parent.id),
                depth=DEPTH_TWO,
                status=STATUS_ACTIVE,
                pg_username="child-admin",
                reseller_profile_id=int(child_prof.id),
            )
            session.add(child)
            await session.flush()
            session.add(
                OrgPrincipalProvision(
                    idempotency_key="l2:test",
                    principal_id=int(child.id),
                    pg_username="child-admin",
                    created_by_principal_id=int(parent.id),
                    status="completed",
                    volume_ceiling_gb=child_ceiling_gb,
                )
            )
            await session.commit()
            return 10, 20, int(parent.id), int(child.id)


class ParentBudgetTests(CascadeHarness):
    async def test_parent_budget_blocks_child_ceiling_raise(self) -> None:
        _ps, _cs, parent_pid, child_pid = await self._tree(
            parent_ceiling_gb=50, child_ceiling_gb=40
        )
        async with self.Session() as session:
            parent = await session.get(OrgPrincipal, parent_pid)
            child = await session.get(OrgPrincipal, child_pid)
            with self.assertRaises(CascadeBudgetError):
                await set_child_volume_ceiling(
                    session,
                    parent_principal=parent,
                    child_principal=child,
                    ceiling_gb=60,
                    actor_principal_id=parent_pid,
                )

    async def test_parent_budget_allows_raise_within_budget(self) -> None:
        _ps, _cs, parent_pid, child_pid = await self._tree(
            parent_ceiling_gb=100, child_ceiling_gb=40
        )
        async with self.Session() as session:
            parent = await session.get(OrgPrincipal, parent_pid)
            child = await session.get(OrgPrincipal, child_pid)
            await set_child_volume_ceiling(
                session,
                parent_principal=parent,
                child_principal=child,
                ceiling_gb=70,
                actor_principal_id=parent_pid,
            )
            await session.commit()
            prov = await session.scalar(
                select(OrgPrincipalProvision).where(
                    OrgPrincipalProvision.principal_id == child_pid
                )
            )
            self.assertEqual(int(prov.volume_ceiling_gb), 70)

    async def test_lower_child_ceiling_below_allocation_rejected(self) -> None:
        _ps, child_shop, parent_pid, child_pid = await self._tree(
            parent_ceiling_gb=100, child_ceiling_gb=40
        )
        async with self.Session() as session:
            session.add(
                BotUser(id=1, telegram_id=1, role=Role.USER.value, referral_code="u1")
            )
            session.add(
                UserService(
                    bot_user_id=1,
                    pg_username="svc",
                    shop_id=child_shop,
                    quota_data_limit_bytes=30 * GB,
                    quota_synced_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            parent = await session.get(OrgPrincipal, parent_pid)
            child = await session.get(OrgPrincipal, child_pid)
            with self.assertRaises(CascadeBudgetError) as ctx:
                await set_child_volume_ceiling(
                    session,
                    parent_principal=parent,
                    child_principal=child,
                    ceiling_gb=10,
                    actor_principal_id=parent_pid,
                )
            self.assertIn("تخصیص", ctx.exception.message)

    async def test_child_cannot_change_own_ceiling(self) -> None:
        _ps, _cs, parent_pid, child_pid = await self._tree()
        async with self.Session() as session:
            parent = await session.get(OrgPrincipal, parent_pid)
            child = await session.get(OrgPrincipal, child_pid)
            with self.assertRaises(CascadeBudgetError):
                await set_child_volume_ceiling(
                    session,
                    parent_principal=parent,
                    child_principal=child,
                    ceiling_gb=50,
                    actor_principal_id=child_pid,
                )

    async def test_delete_child_frees_parent_budget(self) -> None:
        _ps, _cs, parent_pid, child_pid = await self._tree(
            parent_ceiling_gb=50, child_ceiling_gb=40
        )
        async with self.Session() as session:
            total, _ = await sum_children_ceiling_bytes(session, parent_pid)
            self.assertEqual(total, 40 * GB)
            child = await session.get(OrgPrincipal, child_pid)
            child.status = "disabled"
            await session.commit()
            total2, _ = await sum_children_ceiling_bytes(session, parent_pid)
            self.assertEqual(total2, 0)

    async def test_unlimited_child_counts_zero_with_warning(self) -> None:
        _ps, _cs, parent_pid, child_pid = await self._tree(
            parent_ceiling_gb=50, child_ceiling_gb=None
        )
        async with self.Session() as session:
            total, unlimited = await sum_children_ceiling_bytes(session, parent_pid)
            self.assertEqual(total, 0)
            self.assertEqual(len(unlimited), 1)
            self.assertEqual(unlimited[0]["principal_id"], child_pid)

    async def test_parent_gate_includes_children_ceilings(self) -> None:
        parent_shop, _cs, _pp, _cp = await self._tree(
            parent_ceiling_gb=50, child_ceiling_gb=40
        )
        async with self.Session() as session:
            # Parent has 10 GB free for own customers after 40 GB child ceiling.
            await assert_volume_delta_allowed(
                session, shop_id=parent_shop, delta_bytes=10 * GB, audience="admin"
            )
            with self.assertRaises(Exception):
                await assert_volume_delta_allowed(
                    session, shop_id=parent_shop, delta_bytes=11 * GB, audience="admin"
                )

    async def test_l2_buy_extra_checks_parent(self) -> None:
        _ps, _cs, _pp, _cp = await self._tree(
            parent_ceiling_gb=50, child_ceiling_gb=40
        )
        async with self.Session() as session:
            child_prof = await session.scalar(
                select(ResellerProfile).where(ResellerProfile.user_id == 20)
            )
            with self.assertRaises(CascadeBudgetError):
                await assert_l2_extra_gb_against_parent(
                    session, child_profile=child_prof, add_gb=20
                )

    async def test_concurrent_two_children_only_one_fits(self) -> None:
        parent_shop, _cs, parent_pid, child_pid = await self._tree(
            parent_ceiling_gb=50, child_ceiling_gb=20
        )
        async with self.Session() as session:
            # Second child with 40 GB ceiling — only 30 left after first's 20.
            session.add(
                BotUser(id=30, telegram_id=30, role=Role.RESELLER.value, referral_code="c2")
            )
            child2_prof = ResellerProfile(
                user_id=30,
                pg_admin_username="child2-admin",
                billing_mode="fixed",
                allow_volume_oversell=False,
                is_active=True,
            )
            session.add(child2_prof)
            await session.flush()
            child2 = OrgPrincipal(
                parent_id=parent_pid,
                depth=DEPTH_TWO,
                status=STATUS_ACTIVE,
                pg_username="child2-admin",
                reseller_profile_id=int(child2_prof.id),
            )
            session.add(child2)
            await session.flush()
            session.add(
                OrgPrincipalProvision(
                    idempotency_key="l2:test2",
                    principal_id=int(child2.id),
                    pg_username="child2-admin",
                    created_by_principal_id=parent_pid,
                    status="completed",
                    volume_ceiling_gb=20,
                )
            )
            await session.commit()
            parent = await session.get(OrgPrincipal, parent_pid)
            # Raising child2 from 20 → 40 needs +20; parent has 50-20-20=10 free → fail.
            with self.assertRaises(CascadeBudgetError):
                await set_child_volume_ceiling(
                    session,
                    parent_principal=parent,
                    child_principal=child2,
                    ceiling_gb=40,
                    actor_principal_id=parent_pid,
                )

    async def test_sub_admin_without_ceiling_no_limit(self) -> None:
        """Parent with unknown/zero subscription ceiling applies no cascade limit."""
        _ps, _cs, parent_pid, child_pid = await self._tree(
            parent_ceiling_gb=0, child_ceiling_gb=10
        )
        async with self.Session() as session:
            # Remove subscription so parent ceiling is unknown → no cascade.
            sub = await session.scalar(
                select(PgAdminSubscription).where(
                    PgAdminSubscription.pg_username == "parent-admin"
                )
            )
            if sub:
                await session.delete(sub)
                await session.commit()
            parent = await session.get(OrgPrincipal, parent_pid)
            child = await session.get(OrgPrincipal, child_pid)
            await set_child_volume_ceiling(
                session,
                parent_principal=parent,
                child_principal=child,
                ceiling_gb=500,
                actor_principal_id=parent_pid,
            )
            await session.commit()


class MigrationTests(unittest.TestCase):
    def test_migration_upgrade_twice_and_downgrade(self) -> None:
        import sqlalchemy as sa
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        spec = importlib.util.spec_from_file_location(
            "casc_mig", ROOT / "alembic/versions/0067_child_volume_ceiling.py"
        )
        migration = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(migration)
        engine = sa.create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE org_principal_provisions ("
                    "id INTEGER PRIMARY KEY, idempotency_key TEXT, "
                    "principal_id INTEGER, pg_username TEXT, "
                    "created_by_principal_id INTEGER, status TEXT)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO org_principal_provisions "
                    "VALUES (1, 'k', 2, 'c', 1, 'completed')"
                )
            )
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
                migration.upgrade()
                self.assertIsNone(
                    conn.execute(
                        text("SELECT volume_ceiling_gb FROM org_principal_provisions")
                    ).scalar()
                )
                migration.downgrade()
                cols = {
                    c["name"]
                    for c in sa.inspect(conn).get_columns("org_principal_provisions")
                }
                self.assertNotIn("volume_ceiling_gb", cols)
                migration.upgrade()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
