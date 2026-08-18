"""3.3.10 — PG quota gauges: mobile single-col + exhausted banners."""

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

    def test_meter_exhausted_only_at_zero(self):
        low = _meter(
            label="کاربران",
            used=80,
            limit=100,
            used_label="مصرف‌شده",
            remain_label="باقی‌مانده",
            format_value=str,
            kind="count",
        )
        self.assertEqual(low["tone"], "caution")
        self.assertFalse(low["exhausted"])
        self.assertFalse(low["alert"])

        full = _meter(
            label="کاربران",
            used=100,
            limit=100,
            used_label="مصرف‌شده",
            remain_label="باقی‌مانده",
            format_value=str,
            kind="count",
        )
        self.assertEqual(full["remain"], 0)
        self.assertTrue(full["exhausted"])
        self.assertTrue(full["alert"])
        self.assertEqual(full["tone"], "err")

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
        self.assertFalse(m["exhausted"])


class PgQuotaGaugeUiTests(unittest.TestCase):
    def test_macro_no_pulse_has_exhausted(self):
        macro = (ROOT / "app/web/templates/_pg_quota_gauges.html").read_text(encoding="utf-8")
        self.assertIn("home-gauge", macro)
        self.assertNotIn("pg-gauge-pulse", macro)
        self.assertIn("is-exhausted", macro)
        self.assertIn("pg_quota_exhausted_banners", macro)
        self.assertIn("سقف تعداد کاربران پر شده است", macro)
        self.assertIn("سقف حجم تمام شده است", macro)
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn("home-gauge-caution", css)
        self.assertIn(".home-gauge.is-exhausted", css)
        self.assertIn(".pg-quota-gauges", css)
        self.assertIn(".flash.ok::before", css)
        self.assertNotIn("pg-gauge-blink", css)
        self.assertNotIn("pg-gauge-pulse", css)

    def test_mobile_single_column_rectangular(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        block = css.split(".pg-quota-gauges {")[1].split("}")[0]
        self.assertIn("grid-template-columns: 1fr", block)
        gauge = css.split(".pg-quota-gauges .home-gauge {")[1].split("}")[0]
        self.assertIn("flex-direction: column", gauge)
        self.assertIn("height: auto", gauge)

    def test_pg_home_banners_and_order(self):
        src = (ROOT / "app/web/templates/pg_home.html").read_text(encoding="utf-8")
        board_i = src.find("pg_overview_limit_board")
        grid_i = src.find("home-panel-grid")
        self.assertGreater(board_i, 0)
        self.assertGreater(grid_i, board_i)
        self.assertIn("pg-quota-gauges", (ROOT / "app/web/templates/_pg_limit_cards.html").read_text(encoding="utf-8"))
        self.assertIn("staff.pg_is_owner", src)
        self.assertNotIn("{% if not is_admin %}", src)

    def test_reseller_home_banners_at_top(self):
        src = (ROOT / "app/web/templates/reseller_home.html").read_text(encoding="utf-8")
        board_i = src.find("pg_overview_limit_board")
        self.assertGreater(board_i, 0)
        self.assertIn("کیف پول", src)
        self.assertIn("pg_overview_limit_board", src)


if __name__ == "__main__":
    unittest.main()
