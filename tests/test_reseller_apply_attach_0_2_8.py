"""Reseller-apply mode buttons must attach to the main message (no «نوع پلن:» orphan)."""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class ResellerApplyAttachTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_reseller_apply_attaches_inline_to_main_bubble(self):
        from app.bot.handlers.reply_nav import open_reseller_apply
        from app.db.models import Role

        message = AsyncMock()
        main_msg = AsyncMock()
        chrome = AsyncMock()
        chrome.delete = AsyncMock()
        message.answer = AsyncMock(side_effect=[main_msg, chrome])

        session = AsyncMock()
        db_user = MagicMock()
        db_user.role = Role.USER.value

        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📦 ثابت — 1 پلن", callback_data="resapply:mode:fixed")],
                [InlineKeyboardButton(text="⚡ PAYG — 0 پلن", callback_data="resapply:mode:payg")],
            ]
        )

        with (
            patch(
                "app.bot.menu_nav.build_main_reply_keyboard",
                new=AsyncMock(return_value=("MAIN", None, None)),
            ),
            patch(
                "app.bot.handlers.reply_nav.get_all_settings",
                new=AsyncMock(return_value={"menu_order": "shop,reseller_apply"}),
            ),
            patch(
                "app.services.resellers.list_active_reseller_plans",
                new=AsyncMock(side_effect=[[MagicMock()], []]),
            ),
            patch(
                "app.bot.handlers.reseller._resapply_mode_keyboard",
                new=AsyncMock(return_value=markup),
            ),
        ):
            await open_reseller_apply(message, session, db_user)

        self.assertEqual(message.answer.await_count, 2)
        first = message.answer.await_args_list[0]
        self.assertIs(first.kwargs.get("reply_markup"), markup)
        self.assertIn("درخواست نمایندگی", first.args[0])
        second = message.answer.await_args_list[1]
        self.assertEqual(second.kwargs.get("reply_markup"), "MAIN")
        chrome.delete.assert_awaited_once()


class ResellerApplySourceGuards(unittest.TestCase):
    def test_no_orphan_plan_type_caption(self):
        src = Path("app/bot/handlers/reply_nav.py").read_text(encoding="utf-8")
        fn = inspect.getsource(
            __import__(
                "app.bot.handlers.reply_nav", fromlist=["open_reseller_apply"]
            ).open_reseller_apply
        )
        self.assertNotIn('"نوع پلن:"', fn)
        self.assertNotIn("'نوع پلن:'", fn)
        self.assertIn("_resapply_mode_keyboard", fn)


if __name__ == "__main__":
    unittest.main()
