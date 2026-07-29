"""Tests for user menu_order as single source of visibility."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.bot.keyboards import (
    DEFAULT_MENU_ORDER,
    _menu_order,
    main_menu,
    sync_show_flags_for_order,
)


class MenuOrderTests(unittest.TestCase):
    def test_does_not_reinject_removed_items(self):
        ui = {
            "menu_order": "shop,wallet",
            "show_support": "1",
            "show_guide": "1",
            "show_faq": "1",
        }
        self.assertEqual(_menu_order(ui), ["shop", "wallet"])

    def test_shop_always_present(self):
        self.assertEqual(_menu_order({"menu_order": "wallet,support"}), ["shop", "wallet", "support"])

    def test_sync_show_flags(self):
        flags = sync_show_flags_for_order(["shop", "wallet", "faq"])
        self.assertEqual(flags["show_wallet"], "1")
        self.assertEqual(flags["show_faq"], "1")
        self.assertEqual(flags["show_support"], "0")
        self.assertEqual(flags["show_guide"], "0")

    def test_main_menu_follows_order_not_stale_show_flags(self):
        ui = {
            "menu_order": "shop,guide",
            "show_wallet": "1",  # stale — must not appear
            "show_guide": "0",  # stale — guide is in order so must appear
            "btn_shop": "خرید",
            "btn_guide": "راهنما",
            "btn_wallet": "کیف پول",
            "menu_layout": "classic",
            "support_contacts": "[]",
        }
        with patch("app.bot.keyboards.get_settings") as gs:
            gs.return_value.miniapp_enabled = False
            gs.return_value.miniapp_url = ""
            markup = main_menu("user", has_services=False, ui=ui)
        labels = [btn.text for row in markup.inline_keyboard for btn in row]
        self.assertIn("خرید", labels)
        self.assertIn("راهنما", labels)
        self.assertNotIn("کیف پول", labels)

    def test_menu_tab_has_no_display_toggles(self):
        from app.services.users import TAB_SETTING_GROUPS, keys_for_tab

        self.assertEqual(TAB_SETTING_GROUPS.get("menu"), [])
        self.assertEqual(keys_for_tab("menu"), set())


if __name__ == "__main__":
    unittest.main()
