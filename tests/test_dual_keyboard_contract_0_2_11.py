"""Dual-keyboard contract: inline content + matching lasting reply chrome."""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DualKeyboardContractSourceGuards(unittest.TestCase):
    def test_helper_documents_matching_chrome(self):
        from app.bot import tg_utils

        doc = inspect.getdoc(tg_utils.present_inline_with_reply_chrome) or ""
        self.assertIn("Never delete", doc)
        self.assertIn("never force the main menu", doc.lower())

    def test_reseller_apply_not_main_menu_chrome(self):
        from app.bot.handlers import reply_nav

        src = inspect.getsource(reply_nav.open_reseller_apply)
        self.assertIn("reseller_apply_reply_keyboard", src)
        self.assertIn("present_inline_with_reply_chrome", src)
        self.assertNotIn('chrome_text="⌨️ منوی اصلی"', src)
        self.assertNotIn('text="⌨️ منوی اصلی"', src)

    def test_shop_uses_shared_present_helper(self):
        from app.bot.handlers import shop

        src = inspect.getsource(shop.present_shop_kind_picker)
        self.assertIn("present_inline_with_reply_chrome", src)
        self.assertIn("shop_reply_keyboard", src)

    def test_services_list_reply_last(self):
        from app.bot.handlers import reply_nav

        src = inspect.getsource(reply_nav.open_services_list)
        self.assertIn("present_inline_with_reply_chrome", src)

    def test_support_list_reply_last(self):
        from app.bot.handlers import reply_nav

        src = inspect.getsource(reply_nav.open_support_list)
        self.assertIn("present_inline_with_reply_chrome", src)

    def test_support_home_reattaches_after_contacts(self):
        from app.bot.handlers import reply_nav

        src = inspect.getsource(reply_nav.open_support_home)
        self.assertIn("attach_reply_keyboard", src)
        self.assertIn("support_reply_keyboard", src)

    def test_submenu_chrome_keyboard_exists(self):
        from app.bot.reply_keyboards import (
            reseller_apply_reply_keyboard,
            shop_reply_keyboard,
            submenu_chrome_reply_keyboard,
        )

        shop = shop_reply_keyboard({})
        apply = reseller_apply_reply_keyboard({})
        base = submenu_chrome_reply_keyboard({})
        # Not forced-open: Android back can dismiss KB then leave the chat.
        self.assertFalse(shop.is_persistent)
        self.assertFalse(apply.is_persistent)
        self.assertFalse(base.is_persistent)
        # Only back+home footer rows
        self.assertEqual(len(shop.keyboard), 1)
        self.assertEqual(len(apply.keyboard), 1)

    def test_nav_reseller_apply_constant(self):
        from app.bot import menu_nav as nav

        self.assertEqual(nav.NAV_RESELLER_APPLY, "reseller_apply")
        src = Path("app/bot/menu_nav.py").read_text(encoding="utf-8")
        self.assertIn("NAV_RESELLER_APPLY", src)
        self.assertIn("reseller_apply_reply_keyboard", src)


class DualKeyboardPresentHelperTests(unittest.IsolatedAsyncioTestCase):
    async def test_present_sends_inline_then_lasting_reply(self):
        from app.bot.tg_utils import present_inline_with_reply_chrome
        from unittest.mock import AsyncMock, MagicMock

        message = AsyncMock()
        message.answer = AsyncMock(side_effect=[MagicMock(), MagicMock()])
        await present_inline_with_reply_chrome(
            message,
            text="BODY",
            inline="INLINE",
            reply="REPLY",
            chrome_text="⌨️ chrome",
        )
        self.assertEqual(message.answer.await_count, 2)
        self.assertEqual(
            message.answer.await_args_list[0].kwargs.get("reply_markup"), "INLINE"
        )
        self.assertEqual(
            message.answer.await_args_list[1].kwargs.get("reply_markup"), "REPLY"
        )
        self.assertEqual(message.answer.await_args_list[1].args[0], "⌨️ chrome")


if __name__ == "__main__":
    unittest.main()
