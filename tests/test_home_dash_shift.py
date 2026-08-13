"""Home dashboard shift: portals, period sales, work queue."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class HomeDashShiftSurfaceTests(unittest.TestCase):
    def test_ops_partial_and_css(self):
        ops = Path("app/web/templates/_home_ops.html").read_text(encoding="utf-8")
        self.assertIn("home-portal-bot", ops)
        self.assertIn("home-portal-pg", ops)
        self.assertIn("نمای کلی ربات", ops)
        self.assertIn("نمای کلی پاسارگارد", ops)
        self.assertIn("صف کار", ops)
        self.assertIn("ac.entries", ops)
        self.assertIn("day.orders", ops)
        self.assertIn("week.revenue", ops)
        self.assertIn("month.new_users", ops)
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".home-portal-bot", css)
        self.assertIn(".home-period-grid", css)
        self.assertIn("var(--brand)", css[css.find(".home-portal-bot") : css.find(".home-portal-bot") + 400])
        home = Path("app/web/templates/home.html").read_text(encoding="utf-8")
        self.assertIn("_home_ops.html", home)
        self.assertIn("home-gauge", home)
        self.assertIn("home-conn", home)
        self.assertNotIn("home-panel-bot", home)
        api = Path("app/api/home_pages.py").read_text(encoding="utf-8")
        self.assertIn("shop_period_stats", api)
        self.assertIn("build_action_center", api)
        self.assertIn('"periods"', api)
        self.assertIn('"action_center"', api)


class ShopPeriodStatsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.db import Base
        import app.db.models  # noqa: F401

        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "periods.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self._tmpdir.cleanup()

    async def test_period_counts_today_delivered(self):
        from app.db.models import BotUser, Order, Role
        from app.services.home_overview import shop_period_stats

        async with self.Session() as session:
            u = BotUser(
                telegram_id=111001,
                role=Role.USER.value,
                referral_code="P111001",
                wallet_balance=0,
            )
            session.add(u)
            await session.commit()
            await session.refresh(u)
            now = datetime.now(timezone.utc)
            session.add(
                Order(
                    user_id=u.id,
                    amount=50000,
                    status="delivered",
                    reseller_id=None,
                    created_at=now - timedelta(hours=1),
                )
            )
            session.add(
                Order(
                    user_id=u.id,
                    amount=9000,
                    status="pending",
                    reseller_id=None,
                    created_at=now - timedelta(hours=2),
                )
            )
            await session.commit()
            stats = await shop_period_stats(session, reseller_id=None)
            self.assertGreaterEqual(stats["day"]["orders"], 2)
            self.assertGreaterEqual(stats["day"]["delivered"], 1)
            self.assertGreaterEqual(stats["day"]["revenue"], 50000)
            self.assertGreaterEqual(stats["day"]["new_users"], 1)


if __name__ == "__main__":
    unittest.main()
