"""Owner dashboard rendering: KPI strip, status tiles (notice colour/escaping), account card and chart data."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.api.app import templates
from app.services.dashboard_trend import empty_trend

ACTION = {
    "pending": 6, "tickets": 2, "failures": 0, "expiring": 0, "low_volume": 0,
    "has_items": False, "entries": [],
}
PERIODS = {
    "day": {"orders": 3, "delivered": 2, "revenue": 4820, "new_users": 37},
    "week": {"orders": 9, "delivered": 8, "revenue": 9000, "new_users": 182},
    "month": {"orders": 30, "delivered": 28, "revenue": 90000, "new_users": 610},
}


def render(**overrides: object) -> str:
    trend = empty_trend(7)
    trend.update(today=4820, today_change_pct=12, total=9000, has_data=True)
    context = {
        "staff": {"role": "admin", "permissions": [], "pg_permissions": []},
        "overview": {
            "bot": {"ok": True, "unchecked": False, "username": "shop_bot", "error": None},
            "nodes": {"ok": True, "overall": "ok", "connected": 3, "total": 3, "error": None},
        },
        "pg_health": {"ok": True, "unchecked": False, "version": "1.2", "error": None},
        "show_pg_nodes": False, "periods": PERIODS, "action_center": ACTION, "trend": trend,
        "wallet_card": None, "update": None, "pg_limits": None, "funnel_enabled": False,
        "funnel": {}, "dashboard_degraded": False, "widgets_deferred": False,
    }
    context.update(overrides)
    return templates.get_template("_home_dash_body.html").render(**context)


class DashboardRenderTests(unittest.TestCase):
    def test_kpi_strip_shows_today_sales_users_receipts_and_tickets(self) -> None:
        html = render()
        for expected in ("4,820", "37", "182", "12", "رسید منتظر تأیید", "تیکت باز"):
            self.assertIn(expected, html)

    def test_update_notice_is_a_single_warning_tile_only_when_an_update_exists(self) -> None:
        self.assertNotIn("نسخهٔ جدید", render())
        html = render(update={"update_available": True, "remote_version": "0.4.12"})
        self.assertIn("نسخهٔ جدید", html)
        self.assertIn('data-state="warn"', html)
        self.assertIn("has-note", html)

    def test_unhealthy_services_get_their_own_state_and_text_is_escaped(self) -> None:
        html = render(
            overview={"bot": {"ok": False, "unchecked": False, "username": None, "error": "<img src=x onerror=1>"},
                      "nodes": {"ok": True, "overall": "warn", "connected": 2, "total": 3, "error": None}},
            pg_health={"ok": False, "unchecked": False, "version": None, "error": "قطع"},
            show_pg_nodes=True,
        )
        self.assertIn('data-state="err"', html)
        self.assertIn('data-state="warn"', html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("2/3 متصل", html)

    def test_account_card_appears_only_with_wallet_data_and_links_to_that_account(self) -> None:
        self.assertNotIn("حساب من", render())
        card = {"user_id": 7, "balance": 1200, "balance_fa": "", "services": 3, "nearest_expiry_days": 9}
        html = render(wallet_card=card)
        self.assertIn("حساب من", html)
        self.assertIn("/users/7/edit#user-wallet", html)
        self.assertIn("9 روز", html)

    def test_chart_data_is_embedded_and_an_empty_trend_shows_the_empty_message(self) -> None:
        self.assertIn("data-sales-chart", render())
        self.assertIn("data-trend=", render())
        empty = render(trend=empty_trend(7))
        self.assertIn("هنوز فروشی", empty)
        self.assertIn("sales-empty", empty)
