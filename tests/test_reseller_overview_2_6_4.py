"""2.6.4 — reseller/sub-admin bot overview: setup-only + permission gates."""

from __future__ import annotations

import unittest
from pathlib import Path


class ResellerOverviewTests(unittest.TestCase):
    def test_setup_needed_early_return_skips_stats(self):
        src = Path("app/api/app.py").read_text(encoding="utf-8")
        start = src.find("async def dashboard(")
        end = src.find("async def plans_page(", start)
        chunk = src[start:end]
        self.assertIn("bot_needs_setup(profile)", chunk)
        self.assertIn('"bot_setup_needed": True', chunk)
        # Early return before shop aggregates when setup needed
        setup_ret = chunk.find('"bot_setup_needed": True')
        users_agg = chunk.find("BotUser.reseller_id == rid")
        self.assertGreater(setup_ret, 0)
        self.assertGreater(users_agg, setup_ret)

    def test_recent_tables_respect_permissions(self):
        src = Path("app/api/app.py").read_text(encoding="utf-8")
        start = src.find("async def dashboard(")
        end = src.find("async def plans_page(", start)
        chunk = src[start:end]
        self.assertIn('if "payments" in perms:', chunk)
        self.assertIn('if "orders" in perms:', chunk)

    def test_template_gates_quick_links_and_tables(self):
        src = Path("app/web/templates/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("can_payments", src)
        self.assertIn("can_orders", src)
        self.assertIn("can_tickets", src)
        self.assertIn("can_plans", src)
        self.assertIn("can_shop", src)
        # Panels are inside the not-setup branch
        self.assertIn("{% if bot_setup_needed %}", src)
        self.assertIn("{% else %}", src)
        self.assertLess(
            src.find("{% if bot_setup_needed %}"),
            src.find("home-panel-bot"),
        )

    def test_reseller_nav_overview_not_web_dashboard_duplicate(self):
        src = Path("app/web/templates/base.html").read_text(encoding="utf-8")
        # Admin web داشبورد → /home
        self.assertIn('href="/home"', src)
        self.assertIn(">داشبورد</span>", src)
        # Reseller/sub-admin web section has no second داشبورد; bot has نمای کلی
        parts = src.split("nav-section-home")
        non_admin_web = parts[2].split("nav-section-bot")[0]
        self.assertNotIn(">داشبورد</span>", non_admin_web)
        bot = src[src.find("پنل ربات") : src.find("پنل پاسارگارد")]
        self.assertIn(">نمای کلی</span>", bot)
        self.assertIn('href="/dashboard"', bot)


if __name__ == "__main__":
    unittest.main()
