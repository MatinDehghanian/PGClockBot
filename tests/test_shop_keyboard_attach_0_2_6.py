"""v0.2.6/0.2.7 — shop kind/category inline keyboard attaches to the shop bubble."""

from __future__ import annotations

import inspect
import unittest


class ShopKeyboardAttachTests(unittest.TestCase):
    def test_open_shop_list_attaches_inline_via_present_helper(self):
        from app.bot.handlers import reply_nav, shop

        src = inspect.getsource(reply_nav.open_shop_list)
        self.assertIn("present_shop_kind_picker", src)
        self.assertIn('mode="send"', src)
        # Inline kinds live on the present helper (same bubble)
        helper = inspect.getsource(shop.present_shop_kind_picker)
        self.assertIn("shop_kind_keyboard", helper)
        self.assertIn("edit_reply_markup", helper)

    def test_shop_list_callback_edits_without_orphan_caption(self):
        from app.bot.handlers import shop

        src = inspect.getsource(shop.shop_list)
        self.assertIn("present_shop_kind_picker", src)
        self.assertIn('mode="edit"', src)
        self.assertNotIn('"فروشگاه:"', src)


if __name__ == "__main__":
    unittest.main()
