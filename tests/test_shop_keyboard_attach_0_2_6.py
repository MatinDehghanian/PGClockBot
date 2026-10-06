"""v0.2.6 — shop kind/category inline keyboard attaches to the shop bubble."""

from __future__ import annotations

import inspect
import unittest


class ShopKeyboardAttachTests(unittest.TestCase):
    def test_open_shop_list_attaches_inline_to_shop_message(self):
        from app.bot.handlers import reply_nav

        src = inspect.getsource(reply_nav.open_shop_list)
        # Must put shop_kind_keyboard on the shop text message itself
        self.assertIn("shop_kind_keyboard", src)
        self.assertIn('format_message("🛒 فروشگاه"', src)
        # Must not send a detached category caption bubble
        self.assertNotIn('await message.answer(\n        cap,', src)
        self.assertNotIn('await message.answer(\n            cap,', src)
        # Reply chrome still comes from shop_reply_keyboard
        self.assertIn("shop_reply_keyboard", src)

    def test_shop_list_callback_keeps_inline_on_edit(self):
        from app.bot.handlers import shop

        src = inspect.getsource(shop.shop_list)
        self.assertIn("shop_kind_keyboard", src)
        self.assertIn("safe_edit_text", src)


if __name__ == "__main__":
    unittest.main()
