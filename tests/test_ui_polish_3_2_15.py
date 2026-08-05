"""UI polish 3.2.15 — dashboard footer gap, node badges, token focus, flash colors."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
TEMPLATES = ROOT / "app/web/templates"


class DashboardFooterGapTests(unittest.TestCase):
    def test_home_dash_last_child_margin_cleared(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".main-body > :last-child {\n  margin-bottom: 0;\n}", css)
        self.assertIn(".home-dash > :last-child {\n  margin-bottom: 0;\n}", css)


class NodeErrorBadgeTests(unittest.TestCase):
    def test_error_block_does_not_style_badges(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".error:not(.badge) {", css)
        self.assertNotIn("\n.error {\n", css)

    def test_node_status_uses_danger_chip(self):
        nodes = (TEMPLATES / "pg_nodes.html").read_text(encoding="utf-8")
        home = (TEMPLATES / "pg_home.html").read_text(encoding="utf-8")
        self.assertIn("%}danger{", nodes)
        self.assertIn("%}danger{", home)
        self.assertNotIn("%}error{", nodes)
        self.assertNotIn("%}error{", home)


class BotTokenAutofocusTests(unittest.TestCase):
    def test_shop_settings_bot_token_has_no_autofocus(self):
        # Bot token is configured in shop settings / dashboard — not via /rsetup
        src = (TEMPLATES / "shop_settings.html").read_text(encoding="utf-8")
        self.assertIn("ربات اختصاصی", src)
        self.assertFalse((TEMPLATES / "reseller_setup.html").exists())


class FlashSeverityTests(unittest.TestCase):
    def test_bot_setup_is_err_not_warn(self):
        dash = (TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
        rh = (TEMPLATES / "reseller_home.html").read_text(encoding="utf-8")
        self.assertIn('class="flash err dash-bot-setup"', dash)
        self.assertIn('class="flash err dash-bot-setup"', rh)
        self.assertNotIn("flash warn dash-bot-setup", dash)
        self.assertNotIn("flash warn dash-bot-setup", rh)

    def test_update_available_is_warn(self):
        home = (TEMPLATES / "home.html").read_text(encoding="utf-8")
        upd = (TEMPLATES / "_settings_update.html").read_text(encoding="utf-8")
        self.assertIn('class="flash warn home-update-banner"', home)
        self.assertIn(
            'class="flash warn">نسخه جدید آماده است:',
            upd,
        )

    def test_bot_offline_status_is_err(self):
        bot = (TEMPLATES / "_settings_bot.html").read_text(encoding="utf-8")
        shop = (TEMPLATES / "shop_settings.html").read_text(encoding="utf-8")
        self.assertIn("'ok' if bot_status.ok else 'err'", bot)
        self.assertIn("'ok' if bot_status.ok else 'err'", shop)

    def test_appearance_sync_err_is_err(self):
        src = (TEMPLATES / "_settings_appearance.html").read_text(encoding="utf-8")
        self.assertIn('class="flash err"', src)
        self.assertIn("appearance_sync_err", src)


if __name__ == "__main__":
    unittest.main()
