"""v0.2.7 — shop entry must not spam orphan «فروشگاه:» chrome captions."""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


class ShopOrphanCaptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_present_send_sets_chrome_then_inline_on_same_message(self):
        from app.bot.handlers.shop import present_shop_kind_picker

        message = AsyncMock()
        sent = AsyncMock()
        message.answer = AsyncMock(return_value=sent)
        sent.edit_reply_markup = AsyncMock()

        with patch("app.bot.handlers.shop.kb.shop_reply_keyboard", return_value="REPLY"):
            with patch(
                "app.bot.handlers.shop.kb.shop_kind_keyboard", return_value="INLINE"
            ):
                await present_shop_kind_picker(
                    message,
                    ui={},
                    body="body",
                    fixed_on=True,
                    trial_on=False,
                    custom_on=False,
                    wholesale_on=False,
                    mode="send",
                )

        message.answer.assert_awaited_once()
        kwargs = message.answer.await_args.kwargs
        self.assertEqual(kwargs.get("reply_markup"), "REPLY")
        # Must not send a second orphan caption
        self.assertEqual(message.answer.await_count, 1)
        sent.edit_reply_markup.assert_awaited_once_with(reply_markup="INLINE")

    async def test_present_edit_does_not_answer_chrome_caption(self):
        from app.bot.handlers.shop import present_shop_kind_picker

        message = AsyncMock()
        message.answer = AsyncMock()
        with patch("app.bot.handlers.shop.safe_edit_text", new_callable=AsyncMock) as edit:
            with patch(
                "app.bot.handlers.shop.kb.shop_kind_keyboard", return_value="INLINE"
            ):
                await present_shop_kind_picker(
                    message,
                    ui={},
                    body="body",
                    fixed_on=True,
                    trial_on=False,
                    custom_on=False,
                    wholesale_on=False,
                    mode="edit",
                )
        edit.assert_awaited_once()
        message.answer.assert_not_awaited()


class ShopOrphanCaptionSourceGuards(unittest.TestCase):
    def test_no_orphan_shop_caption_answers(self):
        shop = Path("app/bot/handlers/shop.py").read_text(encoding="utf-8")
        reply = Path("app/bot/handlers/reply_nav.py").read_text(encoding="utf-8")
        self.assertNotIn('"فروشگاه:"', shop)
        self.assertNotIn('"فروشگاه:"', reply)
        self.assertNotIn("'فروشگاه:'", shop)
        self.assertNotIn("'فروشگاه:'", reply)

    def test_open_shop_list_uses_present_helper(self):
        from app.bot.handlers import reply_nav

        src = inspect.getsource(reply_nav.open_shop_list)
        self.assertIn("present_shop_kind_picker", src)
        self.assertIn('mode="send"', src)

    def test_shop_list_uses_edit_mode(self):
        from app.bot.handlers import shop

        src = inspect.getsource(shop.shop_list)
        self.assertIn("present_shop_kind_picker", src)
        self.assertIn('mode="edit"', src)


if __name__ == "__main__":
    unittest.main()
