"""3.3.9 — PG quota gauges (users/traffic) like admin CPU/RAM."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.services.pg_overview import _meter, remain_tone


ROOT = Path(__file__).resolve().parents[1]


class RemainToneTests(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(remain_tone(None), "neutral")
        self.assertEqual(remain_tone(100), "ok")
        self.assertEqual(remain_tone(50), "ok")
        self.assertEqual(remain_tone(49.9), "warn")
        self.assertEqual(remain_tone(25), "warn")
        self.assertEqual(remain_tone(24.9), "caution")
        self.assertEqual(remain_tone(10), "caution")
        self.assertEqual(remain_tone(9.9), "err")
        self.assertEqual(remain_tone(0), "err")

    def test_meter_adds_tone_and_remain_pct(self):
        m = _meter(
            label="کاربران",
            used=80,
            limit=100,
            used_label="مصرف‌شده",
            remain_label="باقی‌مانده",
            format_value=str,
            kind="count",
        )
        self.assertTrue(m["has_limit"])
        self.assertEqual(m["pct"], 80.0)
        self.assertEqual(m["remain_pct"], 20.0)
        self.assertEqual(m["tone"], "caution")
        self.assertTrue(m["alert"])

    def test_unlimited_is_neutral(self):
        m = _meter(
            label="حجم",
            used=5,
            limit=None,
            used_label="مصرف‌شده",
            remain_label="باقی‌مانده",
            format_value=str,
            kind="bytes",
        )
        self.assertFalse(m["has_limit"])
        self.assertEqual(m["tone"], "neutral")
        self.assertFalse(m["alert"])


class PgQuotaGaugeUiTests(unittest.TestCase):
    def test_macro_and_css(self):
        macro = (ROOT / "app/web/templates/_pg_quota_gauges.html").read_text(encoding="utf-8")
        self.assertIn("home-gauge", macro)
        self.assertIn("pg-gauge-pulse", macro)
        self.assertIn("remain_pct", macro)
        self.assertIn("باقی‌مانده", macro)
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn("home-gauge-caution", css)
        self.assertIn("pg-gauge-blink", css)
        self.assertIn("--caution-fg", css)

    def test_pg_home_order_and_no_extra_captions(self):
        src = (ROOT / "app/web/templates/pg_home.html").read_text(encoding="utf-8")
        # Gauges section before stats grid
        top_i = src.find("pg-quota-top")
        grid_i = src.find("home-panel-grid")
        self.assertGreater(top_i, 0)
        self.assertGreater(grid_i, top_i)
        # Other boxes no caption lines
        self.assertNotIn("فقط کاربران این حساب", src)
        self.assertNotIn("۲ دقیقه اخیر", src)
        # Users/traffic not duplicated as plain stats
        self.assertNotIn("باقی‌مانده {{ ov.users.remain_text }}", src)
        self.assertNotIn("باقی‌مانده {{ ov.traffic.remain_text }}", src)

    def test_reseller_home_uses_gauges(self):
        src = (ROOT / "app/web/templates/reseller_home.html").read_text(encoding="utf-8")
        self.assertIn("pg_quota_gauge", src)
        self.assertIn("pg-quota-gauges-embed", src)
        # Constraints after gauges; no remain captions on constraint stats
        gauges_i = src.find("pg-quota-gauges-embed")
        cons_i = src.find("pg_limits.constraints")
        self.assertGreater(gauges_i, 0)
        self.assertGreater(cons_i, gauges_i)


if __name__ == "__main__":
    unittest.main()
