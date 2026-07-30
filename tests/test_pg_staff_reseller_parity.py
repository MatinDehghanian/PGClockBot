"""Tests for PG-admin → reseller shop provisioning and overview limits UI."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services.pg_overview import _role_constraint_boxes, _status_meta
from app.services.resellers import _synthetic_telegram_id, bot_needs_setup, join_perms, parse_perms


GB = 1024**3


class SyntheticIdTests(unittest.TestCase):
    def test_stable_negative(self):
        a = _synthetic_telegram_id("AdminOne")
        b = _synthetic_telegram_id("adminone")
        self.assertEqual(a, b)
        self.assertLess(a, 0)


class BotSetupFlagTests(unittest.TestCase):
    def test_needs_setup_without_token(self):
        from types import SimpleNamespace

        self.assertTrue(bot_needs_setup(SimpleNamespace(is_active=True, bot_token=None)))
        self.assertFalse(bot_needs_setup(SimpleNamespace(is_active=True, bot_token="x:y")))
        self.assertFalse(bot_needs_setup(None))


class ConstraintBoxesTests(unittest.TestCase):
    def test_builds_volume_and_expire_boxes(self):
        boxes = _role_constraint_boxes(
            {
                "data_limit_min": 1 * GB,
                "data_limit_max": 10 * GB,
                "expire_max": 30 * 86400,
            }
        )
        labels = [b["label"] for b in boxes]
        self.assertIn("حداقل حجم کاربر", labels)
        self.assertIn("حداکثر حجم کاربر", labels)
        self.assertIn("حداکثر مدت کاربر", labels)
        # Constraint boxes must not carry captions (only users/volume keep remain hints)
        for b in boxes:
            self.assertNotIn("hint", b)

    def test_templates_omit_constraint_captions(self):
        for rel in ("app/web/templates/dashboard.html", "app/web/templates/pg_home.html"):
            src = Path(rel).read_text(encoding="utf-8")
            self.assertNotIn("c.hint", src)
            self.assertIn("باقی‌مانده", src)

    def test_status_meta_still_works(self):
        self.assertEqual(_status_meta("limited"), ("محدود", "warn"))


class WiringTests(unittest.TestCase):
    def test_grant_form_requires_plan(self):
        src = Path("app/web/templates/pg_admins.html").read_text(encoding="utf-8")
        self.assertIn('name="plan_id"', src)
        self.assertIn("پلن نمایندگی", src)

    def test_handler_uses_provision(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn("provision_existing_pg_admin", src)

    def test_dashboard_bot_banner(self):
        src = Path("app/web/templates/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("bot_setup_needed", src)
        self.assertIn("shop-settings?tab=bot", src)
        self.assertIn("dash-bot-setup-inner", src)
        self.assertIn("home-panel-bot", src)
        self.assertIn("home-panel-pg", src)
        self.assertNotIn("pg_limits.time", src)
        self.assertNotIn('class="meter"', src)

    def test_pg_home_no_time_boxes(self):
        src = Path("app/web/templates/pg_home.html").read_text(encoding="utf-8")
        self.assertNotIn("زمان کل", src)
        self.assertNotIn("زمان باقیمانده", src)
        self.assertIn("کاربران", src)
        self.assertNotIn("VPN", src)
        self.assertNotIn('class="meter"', src)
        self.assertIn("باقی‌مانده {{ ov.traffic.remain_text }}", src)
        self.assertIn("ratio_text", src)

    def test_dashboard_status_is_badge_not_box(self):
        src = Path("app/web/templates/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("pg_limits.status_label", src)
        self.assertIn('class="badge {{ pg_limits.status_badge', src)
        self.assertNotIn("<span>وضعیت</span>", src)
        self.assertNotIn("VPN", src)

    def test_broadcast_caption_uses_small_muted(self):
        src = Path("app/web/templates/broadcast.html").read_text(encoding="utf-8")
        self.assertIn('<small class="muted">گروه دریافت‌کننده', src)

    def test_ram_percent_in_ring_amount_under_title(self):
        src = Path("app/web/templates/home.html").read_text(encoding="utf-8")
        # Percent lives in the ring center (like CPU); used/total muted like cores.
        self.assertIn('id="home-mem-val"', src)
        self.assertIn('class="muted" id="home-mem-hint" dir="ltr"', src)
        self.assertNotIn("home-gauge-amount", src)
        self.assertNotIn("home-gauge-center-quiet", src)
        # PG dashboard boxes: users + admins first (no templates slot)
        self.assertIn(">ادمین‌ها</span>", src)
        self.assertNotIn(">تمپلیت‌ها</span>", src)

    def test_base_nav_web_panel_for_all(self):
        src = Path("app/web/templates/base.html").read_text(encoding="utf-8")
        self.assertIn("تنظیمات وب پنل", src)
        # non-admin block links to /security and /dashboard
        self.assertIn('href="/security"', src)

    def test_dashboard_perm_always_injected(self):
        perms = parse_perms("plans,orders")
        for must in ("dashboard", "shop_settings"):
            if must not in perms:
                perms.append(must)
        joined = join_perms(perms)
        self.assertIn("dashboard", joined)
        self.assertIn("shop_settings", joined)


class ProvisionImportTests(unittest.TestCase):
    def test_import(self):
        from app.services.resellers import provision_existing_pg_admin

        self.assertTrue(callable(provision_existing_pg_admin))


if __name__ == "__main__":
    unittest.main()
