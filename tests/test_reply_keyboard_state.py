"""The main menu unfolds the reply keyboard again after the person typed text."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, MessageEntity, User

from app.bot.reply_keyboard_state import (
    KEYBOARD_FOLDED,
    ReplyKeyboardStateMiddleware,
    take_keyboard_folded,
    was_typed,
)
from app.services.users import DEFAULT_SETTINGS

UI = dict(DEFAULT_SETTINGS)
WALLET_LABEL = UI["btn_wallet"]


def _message(text: str, *, chat_type: str = "private", premium: bool = False) -> Message:
    entities = [MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id="1")] if premium else None
    return Message(
        message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=7, type=chat_type),
        from_user=User(id=7, is_bot=False, first_name="u"), text=text, entities=entities,
    )


def _state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=7, user_id=7))


class TypedTextTests(unittest.TestCase):
    def test_typed_text_is_told_apart_from_a_menu_tap(self) -> None:
        self.assertTrue(was_typed(_message("💳 شارژ سریع"), UI))
        self.assertFalse(was_typed(_message(WALLET_LABEL), UI))
        self.assertTrue(was_typed(_message(WALLET_LABEL, premium=True), UI))
        self.assertFalse(was_typed(_message("/start"), UI))
        self.assertFalse(was_typed(_message("سلام", chat_type="supergroup"), UI))


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, message: Message, state: FSMContext) -> AsyncMock:
        handler = AsyncMock(return_value="handled")
        with patch("app.bot.reply_keyboard_state.get_all_settings", AsyncMock(return_value=UI)):
            result = await ReplyKeyboardStateMiddleware()(handler, message, {"state": state, "session": MagicMock()})
        self.assertEqual(result, "handled")
        return handler

    async def test_typing_notes_a_folded_keyboard_and_a_tap_does_not(self) -> None:
        tapped = _state()
        await self._run(_message(WALLET_LABEL), tapped)
        self.assertFalse(await take_keyboard_folded(tapped))
        typed = _state()
        handler = await self._run(_message("متن جدید دکمه"), typed)
        handler.assert_awaited_once()
        self.assertTrue((await typed.get_data())[KEYBOARD_FOLDED])
        self.assertTrue(await take_keyboard_folded(typed))
        self.assertFalse(await take_keyboard_folded(typed))

    async def test_a_failing_settings_read_never_blocks_the_message(self) -> None:
        handler = AsyncMock(return_value="handled")
        with patch("app.bot.reply_keyboard_state.get_all_settings", AsyncMock(side_effect=RuntimeError)):
            result = await ReplyKeyboardStateMiddleware()(handler, _message("x"), {"state": _state(), "session": MagicMock()})
        self.assertEqual(result, "handled")


class HomeAfterTypingTests(unittest.IsolatedAsyncioTestCase):
    async def _go_home(self, state: FSMContext) -> tuple[AsyncMock, AsyncMock]:
        from app.bot.handlers import start

        callback = MagicMock()
        callback.answer = AsyncMock()
        with (
            patch.object(start, "render_home", AsyncMock()) as render,
            patch.object(start, "delete_user_message", AsyncMock()) as delete,
        ):
            await start.cb_home(callback, MagicMock(), MagicMock(), state)
        return render, delete

    async def test_after_typing_the_main_menu_is_a_new_message_that_unfolds_the_keyboard(self) -> None:
        state = _state()
        await state.update_data({KEYBOARD_FOLDED: True})
        render, delete = await self._go_home(state)
        self.assertFalse(render.await_args.kwargs["edit"])
        delete.assert_awaited_once()
        render, delete = await self._go_home(state)
        self.assertTrue(render.await_args.kwargs["edit"])
        delete.assert_not_awaited()

    def test_the_bot_dispatcher_runs_the_middleware_for_every_message(self) -> None:
        import app.bot as bot_package

        routers = bot_package.bot_routers()
        for router in routers:
            router._parent_router = None
        try:
            dp = bot_package.create_dispatcher()
            self.assertTrue(any(isinstance(m, ReplyKeyboardStateMiddleware) for m in dp.message.outer_middleware))
        finally:
            for router in routers:
                router._parent_router = None


if __name__ == "__main__":
    unittest.main()
