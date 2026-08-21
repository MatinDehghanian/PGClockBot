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
        self.assertIn("@container home-periods", css)
        go = css[css.find(".home-portal-go") : css.find(".home-portal-go") + 420]
        self.assertIn("place-items: center", go)
        self.assertIn("home-portal-go svg", css)
        self.assertNotIn("تقویم تهران", ops)
        self.assertIn("<svg viewBox=\"0 0 24 24\"><path d=\"M15 6l-6 6 6 6\"/></svg>", ops)
        self.assertIn("var(--bot-line)", css[css.find(".home-portal-bot") : css.find(".home-portal-bot") + 400])
        home = Path("app/web/templates/_home_dash_body.html").read_text(encoding="utf-8")
        self.assertIn("_home_ops.html", home)
        self.assertNotIn("home-gauge", home)
        self.assertNotIn("/home/metrics", home)
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
        from app.services.home_overview import _period_since_utc, shop_period_stats

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
            starts = _period_since_utc()
            # Anchor inside Tehran «today» so day/week/month all see the rows.
            inside_today = starts["day"] + timedelta(hours=2)
            session.add(
                Order(
                    user_id=u.id,
                    amount=50000,
                    status="delivered",
                    reseller_id=None,
                    created_at=inside_today,
                )
            )
            session.add(
                Order(
                    user_id=u.id,
                    amount=9000,
                    status="pending",
                    reseller_id=None,
                    created_at=inside_today + timedelta(minutes=5),
                )
            )
            # Outside 30d window — must not inflate month aggregates.
            session.add(
                Order(
                    user_id=u.id,
                    amount=1000,
                    status="delivered",
                    reseller_id=None,
                    created_at=starts["month"] - timedelta(days=15),
                )
            )
            u.created_at = inside_today
            await session.commit()
            stats = await shop_period_stats(session, reseller_id=None)
            self.assertEqual(stats["day"]["orders"], 2)
            self.assertEqual(stats["day"]["delivered"], 1)
            self.assertEqual(stats["day"]["revenue"], 50000)
            self.assertGreaterEqual(stats["day"]["new_users"], 1)
            self.assertEqual(stats["week"]["orders"], 2)
            self.assertEqual(stats["month"]["orders"], 2)
            self.assertEqual(stats["month"]["revenue"], 50000)

    async def test_period_stats_uses_two_queries(self):
        src = Path("app/services/home_overview.py").read_text(encoding="utf-8")
        fn = src[src.find("async def shop_period_stats") : src.find("def _empty_bot_summary")]
        self.assertIn("Two aggregated queries", fn)
        self.assertIn("func.sum(case(", fn)
        # No per-period count loop.
        self.assertNotIn("for key, since in starts.items()", fn)


if __name__ == "__main__":
    unittest.main()
