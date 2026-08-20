"""Message variables catalog + safe domain rendering."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.bot.middlewares import force_join_block_message
from app.services.message_variables import (
    DOMAIN_FORCE_JOIN,
    DOMAIN_PAYMENT,
    DOMAIN_USER,
    catalog_groups,
    render_message_template,
)
from app.services.safe_format import looks_like_format_injection, safe_format


ROOT = Path(__file__).resolve().parents[1]


class MessageVariablesCatalogTests(unittest.TestCase):
    def test_catalog_has_persian_groups(self):
        groups = catalog_groups(include_owner_only=True)
        labels = [g["label"] for g in groups]
        self.assertTrue(any("فروشگاه" in x for x in labels))
        self.assertTrue(any("پرداخت" in x for x in labels))
        keys = {v["key"] for g in groups for v in g["vars"]}
        self.assertIn("user_name", keys)
        self.assertIn("gateway_name", keys)
        self.assertIn("channels", keys)

    def test_reseller_catalog_hides_naming(self):
        groups = catalog_groups(include_owner_only=False)
        keys = {v["key"] for g in groups for v in g["vars"]}
        self.assertNotIn("prefix", keys)
        self.assertNotIn("random", keys)

    def test_sidebar_before_settings(self):
        src = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
        bot = src.split("nav-section-bot", 1)[1].split("nav-section-pg", 1)[0]
        self.assertLess(bot.find("/message-variables"), bot.find(">تنظیمات</span>"))

    def test_page_template_exists(self):
        self.assertTrue((ROOT / "app/web/templates/message_variables.html").exists())
        html = (ROOT / "app/web/templates/message_variables.html").read_text(encoding="utf-8")
        self.assertIn("msg-vars-token", html)
        # Intro examples must use HTML entities — never raw {name} in template source.
        self.assertNotIn("{name}", html)
        self.assertNotIn("{order_id}", html)
        self.assertIn("&#123;order_id&#125;", html)

    def test_page_requires_shop_settings(self):
        src = (ROOT / "app/api/message_variables_pages.py").read_text(encoding="utf-8")
        self.assertIn('require_perm("shop_settings")', src)
        self.assertIn("include_owner_only", src)
        self.assertIn("is_explicit_owner_staff", src)
        self.assertNotIn("BOT_TOKEN", src)
        self.assertNotIn("ADMIN_IDS", src)


class MessageVariablesRenderTests(unittest.TestCase):
    def test_user_name_alias_and_html_escape(self):
        out = render_message_template(
            "سلام {name} / {user_name}",
            domain=DOMAIN_USER,
            user_name="<b>Ali</b>",
        )
        self.assertEqual(out, "سلام &lt;b&gt;Ali&lt;/b&gt; / &lt;b&gt;Ali&lt;/b&gt;")

    def test_domain_isolation_no_leak(self):
        out = render_message_template(
            "pay {user_name} {amount}",
            domain=DOMAIN_PAYMENT,
            user_name="SECRET",
            amount="۱۰ تومان",
            gateway_name="Gate",
        )
        self.assertEqual(out, "pay {user_name} ۱۰ تومان")

    def test_gateway_name_alias(self):
        out = render_message_template(
            "از {name} / {gateway_name}",
            domain=DOMAIN_PAYMENT,
            gateway_name="زرین",
        )
        self.assertEqual(out, "از زرین / زرین")

    def test_injection_not_evaluated(self):
        evil = "{order_id.__class__}"
        self.assertTrue(looks_like_format_injection(evil))
        self.assertEqual(safe_format(evil, order_id=1), evil)

    def test_force_join_uses_safe_renderer(self):
        src = (ROOT / "app/bot/middlewares.py").read_text(encoding="utf-8")
        self.assertIn("render_message_template", src)
        self.assertNotIn(".format(channels=", src)
        msg = force_join_block_message(
            ["@a"], custom="عضو شوید:\n{channels}"
        )
        self.assertIn("• @a", msg)
        # XSS-ish channel label escaped
        msg2 = force_join_block_message(
            ["<script>"], custom="{channels}"
        )
        self.assertIn("&lt;script&gt;", msg2)
        self.assertNotIn("<script>", msg2)


if __name__ == "__main__":
    unittest.main()
