"""2.6.5 — reseller web dashboard vs bot overview split (like admin)."""

from __future__ import annotations

import unittest
from pathlib import Path


class ResellerNavSplitTests(unittest.TestCase):
    def test_reseller_web_dashboard_and_bot_overview_links(self):
        src = Path("app/web/templates/base.html").read_text(encoding="utf-8")
        parts = src.split("nav-section-home")
        non_admin_web = parts[2].split("nav-section-bot")[0]
        self.assertIn('href="/home"', non_admin_web)
        self.assertIn(">داشبورد</span>", non_admin_web)
        bot = src[src.find("پنل ربات") : src.find("پنل پاسارگارد")]
        self.assertIn('href="/dashboard"', bot)
        self.assertIn(">نمای کلی</span>", bot)

    def test_bot_overview_has_no_pg_panel(self):
        dash = Path("app/web/templates/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("home-panel-bot", dash)
        self.assertNotIn("home-panel-pg", dash)
        self.assertNotIn("pg_limits", dash)

    def test_reseller_home_has_bot_and_pg_panels(self):
        home = Path("app/web/templates/reseller_home.html").read_text(encoding="utf-8")
        self.assertIn("home-panel-bot", home)
        self.assertIn("home-panel-pg", home)
        self.assertIn("pg_limits", home)
        self.assertIn('href="/dashboard"', home)
        self.assertIn("page_title('home', 'داشبورد', 'neutral')", home)
        self.assertIn("home-conn-card", home)
        self.assertIn("وضعیت اتصال", home)
        self.assertIn('href="/shop-settings?tab=bot"', home)
        self.assertIn("bot.ok", home)

    def test_home_route_serves_reseller_template(self):
        src = Path("app/api/home_pages.py").read_text(encoding="utf-8")
        self.assertIn("require_staff", src)
        self.assertIn("reseller_home.html", src)
        self.assertIn("is_platform_admin", src)
        self.assertIn("build_reseller_pg_overview", src)
        self.assertIn("check_bot_connection", src)
        self.assertIn('"bot": bot', src)

    def test_dashboard_route_does_not_fetch_pg_limits(self):
        src = Path("app/api/app.py").read_text(encoding="utf-8")
        start = src.find("async def dashboard(")
        end = src.find("async def plans_page(", start)
        chunk = src[start:end]
        self.assertNotIn("build_reseller_pg_overview", chunk)
        self.assertNotIn("pg_limits", chunk)
        self.assertIn("bot_needs_setup", chunk)


if __name__ == "__main__":
    unittest.main()
