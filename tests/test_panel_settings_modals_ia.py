"""Panel IA: domain settings modals + finance hub."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app/web/templates"


class DomainSettingsRedirectTests(unittest.TestCase):
    def test_bot_settings_tabs_slimmed(self):
        from app.services.users import SETTINGS_DOMAIN_REDIRECTS, SETTINGS_TABS

        keys = {k for k, _ in SETTINGS_TABS}
        for removed in ("payment", "supports", "billing"):
            self.assertNotIn(removed, keys)
            self.assertIn(removed, SETTINGS_DOMAIN_REDIRECTS)
        self.assertIn("loyalty", SETTINGS_DOMAIN_REDIRECTS)

    def test_shop_settings_tabs_slimmed(self):
        from app.services.resellers import (
            RESELLER_SETTINGS_TABS,
            SHOP_SETTINGS_DOMAIN_POST_TABS,
            SHOP_SETTINGS_DOMAIN_REDIRECTS,
        )

        keys = {k for k, _ in RESELLER_SETTINGS_TABS}
        self.assertNotIn("payment", keys)
        self.assertNotIn("supports", keys)
        self.assertEqual(
            set(SHOP_SETTINGS_DOMAIN_REDIRECTS),
            set(SHOP_SETTINGS_DOMAIN_POST_TABS),
        )
        self.assertIn("loyalty", SHOP_SETTINGS_DOMAIN_REDIRECTS)

    def test_nav_has_finance_not_separate_orders_payments(self):
        src = (TEMPLATES / "base.html").read_text(encoding="utf-8")
        self.assertIn('href="/finance"', src)
        self.assertIn("مدیریت مالی", src)
        # Separate sidebar entries for orders/payments removed
        self.assertNotRegex(src, r'href="/orders"\s+class="nav-item')
        self.assertNotRegex(src, r'href="/payments"\s+class="nav-item')


class DomainModalTemplateTests(unittest.TestCase):
    def test_finance_page_modal(self):
        html = (TEMPLATES / "finance.html").read_text(encoding="utf-8")
        self.assertIn('data-modal-open="modal-finance-settings"', html)
        self.assertIn("section-tabs", html)
        self.assertIn("_modal_finance_settings.html", html)
        self.assertTrue((TEMPLATES / "_modal_finance_settings.html").is_file())

    def test_tickets_supports_modal(self):
        html = (TEMPLATES / "tickets.html").read_text(encoding="utf-8")
        self.assertIn("پشتیبان‌ها", html)
        self.assertIn('data-modal-open="modal-supports-settings"', html)
        self.assertIn("_modal_supports_settings.html", html)

    def test_loyalty_settings_modal_not_page_tab(self):
        html = (TEMPLATES / "loyalty.html").read_text(encoding="utf-8")
        self.assertIn('data-modal-open="modal-loyalty-settings"', html)
        self.assertIn("section-tabs", html)
        self.assertNotIn("tabs tabs-scroll", html)
        self.assertNotIn('href="/loyalty?tab=settings"', html)
        self.assertIn("_modal_loyalty_settings.html", html)
        modal = (TEMPLATES / "_modal_loyalty_settings.html").read_text(encoding="utf-8")
        self.assertIn('data-modal-tab="club"', modal)
        self.assertIn('data-modal-tab="referral"', modal)

    def test_settings_html_no_supports_or_payment_branches(self):
        html = (TEMPLATES / "settings.html").read_text(encoding="utf-8")
        self.assertNotIn("tab == 'supports'", html)
        self.assertNotIn("tab == 'payment'", html)

    def test_legacy_order_payment_templates_removed(self):
        self.assertFalse((TEMPLATES / "orders.html").exists())
        self.assertFalse((TEMPLATES / "payments.html").exists())

    def test_modal_tab_js_and_css(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn("data-modal-tabs", js)
        self.assertIn("data-modal-tab-panel", js)
        self.assertIn("settings-modal-panel", css)
        self.assertIn(".section-tabs .tab-btn", css)


class DomainSettingGroupsTests(unittest.TestCase):
    def test_support_and_referral_groups_split(self):
        from app.services.users import SETTING_GROUPS, TAB_SETTING_GROUPS, keys_for_tab

        self.assertIn("متن پشتیبانی ربات", SETTING_GROUPS)
        self.assertIn("متن دعوت دوستان", SETTING_GROUPS)
        msg_keys = {f[0] for f in SETTING_GROUPS["متن پیام‌ها"]}
        self.assertNotIn("support_text", msg_keys)
        self.assertNotIn("referral_text", msg_keys)
        self.assertEqual(keys_for_tab("supports"), {"support_text"})
        self.assertEqual(keys_for_tab("loyalty"), {"referral_text"})
        self.assertIn("روش‌های پرداخت", TAB_SETTING_GROUPS["payment"])


if __name__ == "__main__":
    unittest.main()
