"""Inline settings «⬅️ بازگشت» must go back to the hub, not Owner-alert.

The subsection back button is navigation. Previous Owner-gate wiring on
``adm:settings`` trapped the real operator with «دسترسی مالک سیستم لازم است»
even after they had already opened Settings from the reply keyboard.
"""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from aiogram.dispatcher.event.handler import CallableObject

from app.bot import _RequireBotOwnerPrincipal, _SETTINGS_NAV_BACK
from app.bot.auth import OWNER_REQUIRED_MESSAGE, require_bot_owner_handler
from app.bot.handlers.admin_settings import settings_hub


def _cb(data: str = "adm:st:hub"):
    cb = AsyncMock()
    cb.data = data
    cb.message = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


class InlineSettingsBackTests(unittest.IsolatedAsyncioTestCase):
    def test_hub_handler_takes_session_in_real_signature(self):
        inner = inspect.signature(settings_hub)
        self.assertIn("session", inner.parameters)
        self.assertEqual(
            inner.parameters["session"].kind, inspect.Parameter.POSITIONAL_OR_KEYWORD
        )

    def test_aiogram_callable_object_sees_session_for_settings_hub(self):
        co = CallableObject(callback=settings_hub)
        self.assertIn("session", co.params)
        self.assertIn("callback", co.params)

    def test_section_inline_back_is_return_not_owner_gate(self):
        src = open("app/bot/handlers/admin_settings.py", encoding="utf-8").read()
        self.assertIn('("⬅️ بازگشت", "adm:st:hub")', src)
        self.assertNotIn('("⬅️ تنظیمات", "adm:settings")', src)
        self.assertNotIn("@require_bot_owner_handler\nasync def settings_hub", src)
        self.assertIn("adm:st:hub", _SETTINGS_NAV_BACK)
        self.assertIn("adm:settings", _SETTINGS_NAV_BACK)

    async def test_owner_back_edits_hub_without_owner_alert(self):
        cb = _cb("adm:st:hub")
        session = MagicMock(spec=AsyncSession)
        db_user = SimpleNamespace(role="admin", telegram_id=42)
        await settings_hub(cb, session, db_user)
        cb.answer.assert_awaited()
        if cb.answer.await_args.args:
            self.assertNotEqual(cb.answer.await_args.args[0], OWNER_REQUIRED_MESSAGE)
        cb.message.edit_text.assert_awaited()
        text = cb.message.edit_text.await_args.args[0]
        self.assertIn("تنظیمات", text)
        cb.message.answer.assert_not_awaited()

    async def test_legacy_adm_settings_callback_also_goes_back(self):
        cb = _cb("adm:settings")
        session = MagicMock(spec=AsyncSession)
        db_user = SimpleNamespace(role="user", telegram_id=9)
        await settings_hub(cb, session, db_user)
        cb.answer.assert_awaited()
        cb.message.edit_text.assert_awaited()
        cb.message.answer.assert_not_awaited()

    async def test_owner_middleware_skips_settings_back_without_alert(self):
        ran = {}

        async def nxt(event, data):
            ran["ok"] = True
            return "hub"

        mw = _RequireBotOwnerPrincipal()
        cb = SimpleNamespace(data="adm:st:hub", answer=AsyncMock())
        out = await mw(nxt, cb, {"session": None, "db_user": None})
        self.assertEqual(out, "hub")
        self.assertTrue(ran.get("ok"))
        cb.answer.assert_not_awaited()

    async def test_owner_middleware_still_alerts_on_real_admin_actions(self):
        async def nxt(event, data):
            raise AssertionError("must not run")

        mw = _RequireBotOwnerPrincipal()
        cb = SimpleNamespace(data="adm:st:sec:shop", answer=AsyncMock())
        out = await mw(nxt, cb, {"session": None, "db_user": None, "is_reseller_bot": False})
        self.assertIsNone(out)
        cb.answer.assert_awaited()
        self.assertEqual(cb.answer.await_args.args[0], OWNER_REQUIRED_MESSAGE)
        self.assertTrue(cb.answer.await_args.kwargs.get("show_alert"))

    def test_decorator_still_adds_session_when_handler_omits_it(self):
        @require_bot_owner_handler
        async def _hub(callback, state, db_user):
            return "ok"

        sig = inspect.signature(_hub)
        self.assertIn("session", sig.parameters)
        self.assertFalse(hasattr(_hub, "__wrapped__"))


if __name__ == "__main__":
    unittest.main()
