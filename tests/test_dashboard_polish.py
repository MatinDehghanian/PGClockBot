"""Dashboard overview polish — گیگ label, sticky footer, equal boxes."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.services.formatting import format_bytes, format_gb


class FormatGigLabelTests(unittest.TestCase):
    def test_gb_is_persian_gig(self):
        text = format_bytes(5 * (1024**3))
        self.assertIn("گیگ", text)
        self.assertNotIn("GB", text)

    def test_format_gb_uses_gig(self):
        self.assertIn("گیگ", format_gb(10))
        self.assertNotIn("GB", format_gb(10))

    def test_unlimited(self):
        self.assertEqual(format_bytes(None), "نامحدود")


class DashboardPolishSourceTests(unittest.TestCase):
    def test_bot_setup_centered(self):
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".dash-bot-setup-inner", css)
        self.assertIn("justify-content: center", css)
        self.assertIn(".site-footer {\n  margin-top: auto;", css)

    def test_overview_boxes_equal_and_rtl(self):
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn("height: 96px", css)
        self.assertIn(".home-panel-grid > .stat strong", css)
        self.assertIn("text-align: right", css)

    def test_home_and_dashboard_share_panel_classes(self):
        home = Path("app/web/templates/home.html").read_text(encoding="utf-8")
        dash = Path("app/web/templates/dashboard.html").read_text(encoding="utf-8")
        for cls in ("home-panels", "home-panel-bot", "home-panel-pg", "home-panel-grid"):
            self.assertIn(cls, home)
            self.assertIn(cls, dash)


if __name__ == "__main__":
    unittest.main()
