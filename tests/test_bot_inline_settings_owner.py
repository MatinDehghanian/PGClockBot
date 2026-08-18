"""Inline settings back button must not false-deny the real Owner.

``adm:settings`` (⬅️ تنظیمات) hits ``settings_hub``, which omitted ``session``
from its handler signature. Aiogram follows ``inspect.signature`` through
``__wrapped__``, so the decorator never received the request session and
fail-closed with «دسترسی مالک سیستم لازم است» even for ADMIN_IDS owners.
Reply-keyboard settings still worked because reply-nav passed session itself.
"""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.auth import require_bot_owner_handler
from app.bot.handlers.admin_settings import settings_hub


class InlineSettingsOwnerGateTests(unittest.IsolatedAsyncioTestCase):
    def test_settings_hub_exposes_session_for_aiogram_di(self):
        sig = inspect.signature(settings_hub)
        self.assertIn("session", sig.parameters)
        self.assertEqual(sig.parameters["session"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_decorator_adds_session_when_handler_omits_it(self):
        @require_bot_owner_handler
        async def _hub(callback, state, db_user):
            return "ok"

        sig = inspect.signature(_hub)
        self.assertIn("session", sig.parameters)
        self.assertIn("callback", sig.parameters)
        self.assertNotIn("session", inspect.signature(_hub.__wrapped__).parameters)

    async def test_owner_inline_settings_with_injected_session_reaches_hub(self):
        cb = AsyncMock()
        cb.data = "adm:settings"
        cb.message = AsyncMock()
        cb.message.edit_text = AsyncMock()
        cb.message.answer = AsyncMock()
        cb.answer = AsyncMock()
        state = AsyncMock()
        state.clear = AsyncMock()
        db_user = SimpleNamespace(role="admin", telegram_id=42)
        session = MagicMock(spec=AsyncSession)

        with patch("app.bot.auth.require_bot_owner", AsyncMock(return_value=True)) as gate:
            await settings_hub(cb, state, db_user, session=session)

        gate.assert_awaited()
        self.assertIs(gate.await_args.args[0], session)
        cb.answer.assert_awaited()
        cb.message.edit_text.assert_awaited()

    async def test_owner_handler_does_not_forward_session_to_omitting_fn(self):
        ran = {}

        @require_bot_owner_handler
        async def _hub(callback, db_user):
            ran["ok"] = True
            return "ok"

        cb = AsyncMock()
        cb.data = "adm:settings"
        db_user = SimpleNamespace(role="admin", telegram_id=1)
        session = MagicMock(spec=AsyncSession)
        with patch("app.bot.auth.require_bot_owner", AsyncMock(return_value=True)):
            out = await _hub(cb, db_user, session=session)
        self.assertEqual(out, "ok")
        self.assertTrue(ran.get("ok"))

    async def test_missing_session_still_fail_closes(self):
        cb = AsyncMock()
        cb.data = "adm:settings"
        cb.answer = AsyncMock()
        db_user = SimpleNamespace(role="admin", telegram_id=1)
        with patch(
            "app.bot.auth.require_bot_owner", AsyncMock(return_value=False)
        ) as gate:
            out = await settings_hub(cb, AsyncMock(), db_user)
        self.assertIsNone(out)
        self.assertIsNone(gate.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
