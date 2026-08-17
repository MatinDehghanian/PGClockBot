"""UX pulse + panel speed: shell-first home, fonts, caches, empty states."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HomePulseSurfaceTests(unittest.TestCase):
    def test_home_has_pulse_wallet_and_live(self):
        home = (ROOT / "app/web/templates/home.html").read_text(encoding="utf-8")
        self.assertIn("home-pulse", home)
        self.assertIn("wallet_card", home)
        self.assertIn("data-home-live", home)
        self.assertIn("/home/live", (ROOT / "app/api/home_pages.py").read_text(encoding="utf-8"))
        self.assertIn("build_home_shell", (ROOT / "app/api/home_pages.py").read_text(encoding="utf-8"))
        self.assertNotIn("host.cpu_percent", home)

    def test_ops_action_before_portals(self):
        ops = (ROOT / "app/web/templates/_home_ops.html").read_text(encoding="utf-8")
        self.assertLess(ops.find("صف کار"), ops.find("home-portal-bot"))
        self.assertIn("empty_state", ops)
        self.assertIn("day.orders", ops)
        self.assertIn("week.revenue", ops)
        self.assertIn("month.new_users", ops)

    def test_reseller_home_wallet(self):
        src = (ROOT / "app/web/templates/reseller_home.html").read_text(encoding="utf-8")
        self.assertIn("home-wallet-card", src)
        self.assertIn("home-pulse", src)


class SpeedHooksTests(unittest.TestCase):
    def test_gzip_and_self_hosted_fonts(self):
        api = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("GZipMiddleware", api)
        self.assertIn("font-src 'self' data:", api)
        self.assertNotIn("fonts.googleapis.com", api)
        self.assertIn("/static/fonts.css", (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8"))

    def test_pg_get_cache_keyed_by_identity(self):
        src = (ROOT / "app/services/pasarguard.py").read_text(encoding="utf-8")
        self.assertIn("_read_cache_ident", src)
        self.assertIn("cache_get", src)
        cache = (ROOT / "app/services/pg_read_cache.py").read_text(encoding="utf-8")
        self.assertIn("invalidate_ident", cache)
        self.assertIn("_TTL_SEC = 4.0", cache)

    def test_sidebar_unread_cache_and_live_skip(self):
        from app.services.panel_tickets import SKIP_UNREAD_PATHS, should_skip_unread_count

        self.assertIn("/home/live", SKIP_UNREAD_PATHS)
        self.assertTrue(should_skip_unread_count("/home/live", "GET"))
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("peek_sidebar_counts", src)

    def test_panel_nav_swap_same_origin(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("panelNavigate", js)
        self.assertIn("X-Panel-Nav", js)
        self.assertIn("canPanelNav", js)
        self.assertIn("/logout", js)


class MiniappPulseTests(unittest.TestCase):
    def test_service_first_home_and_fonts(self):
        js = (ROOT / "app/web/static/miniapp.js").read_text(encoding="utf-8")
        self.assertIn("سرویسی ندارید", js)
        self.assertIn("data-goto=\"shop\"", js)
        html = (ROOT / "app/web/templates/miniapp.html").read_text(encoding="utf-8")
        self.assertIn("/static/fonts.css", html)
        self.assertNotIn("fonts.googleapis.com", html)


class UserFacingErrorTests(unittest.TestCase):
    def test_pg_outage_is_actionable(self):
        from app.services.user_facing_errors import user_facing_error

        self.assertIn("پاسارگارد", user_facing_error("pg_outage"))
        self.assertNotIn("Traceback", user_facing_error("boom\nTraceback"))


class HomePulseUnitTests(unittest.TestCase):
    def test_pulse_warn_when_queue(self):
        from app.services.home_overview import build_home_pulse

        p = build_home_pulse(
            periods={"day": {"delivered": 2, "revenue": 1}},
            action_center={"has_items": True, "tickets": 3, "pending": 1, "expiring": 0},
        )
        self.assertEqual(p["tone"], "warn")
        self.assertEqual(p["delivered"], 2)


if __name__ == "__main__":
    unittest.main()
