"""Customer refresh acknowledgements, safe errors and main-menu discoverability."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from aiogram.types import CallbackQuery, Chat, Message, User

from connection_monitor_support import MonitorDatabaseCase

from app.bot import keyboards
from app.bot.connection_status_public_ui import public_cursor
from app.bot.connection_status_ui import monitor_text
from app.bot.handlers import connection_status as handler
from app.services.connection_status import PublicConnectionPage
from app.services.connection_status_texts import MONITOR_TEXT_DEFAULTS
from app.services.message_variables import template_variable_specs
from app.services.users import DEFAULT_SETTINGS


class PublicStatusBotTests(MonitorDatabaseCase):
    def message(self) -> Message:
        return Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=101, type="private"),
                       from_user=User(id=101, is_bot=False, first_name="Customer"), text="وضعیت")

    async def test_refresh_acknowledges_before_reading_and_empty_state_is_safe(self) -> None:
        message = self.message()
        callback = CallbackQuery(id="callback", from_user=message.from_user, message=message, chat_instance="synthetic", data="csp:refresh")
        with patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer:
            async def read(*args: object, **kwargs: object) -> PublicConnectionPage:
                self.assertEqual(answer.await_count, 1)
                return PublicConnectionPage(())
            with patch.object(handler, "public_connection_page", side_effect=read):
                with patch.object(handler, "safe_edit_text", new_callable=AsyncMock) as edit:
                    async with self.Session() as session:
                        await handler.refresh_connection_status(callback, session)
                    self.assertIn(DEFAULT_SETTINGS["connection_status_empty"], edit.call_args.args[1])
                    self.assertIn("بررسی از سرور ربات", edit.call_args.args[1])

    async def test_read_failure_does_not_echo_database_or_panel_payload(self) -> None:
        with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
            with patch.object(handler, "public_connection_page", AsyncMock(side_effect=RuntimeError("sensitive-token-and-address"))):
                async with self.Session() as session:
                    await handler._show(self.message(), session, after_id=0, edit=False)
                text = answer.call_args.args[0]
                self.assertEqual(text, DEFAULT_SETTINGS["connection_status_error"])
                self.assertNotIn("sensitive", text)

    async def test_status_is_discoverable_on_reply_and_inline_customer_menus(self) -> None:
        ui = dict(DEFAULT_SETTINGS)
        reply = keyboards.main_reply_keyboard("user", has_services=False, ui=ui)
        self.assertIn(ui["btn_connection_status"], [button.text for row in reply.keyboard for button in row])
        inline = keyboards.main_menu("user", has_services=False, ui=ui)
        self.assertIn("csp:refresh", [button.callback_data for row in inline.inline_keyboard for button in row])

    async def test_refresh_callback_never_accepts_a_shop_identifier_or_unbounded_cursor(self) -> None:
        self.assertEqual(public_cursor("csp:refresh"), 0)
        self.assertEqual(public_cursor("csp:next:10"), 10)
        for raw in ("csp:next:-1", "csp:shop:2", "csp:next:1:2", "csp:next:2147483648", "csp:next:True"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                public_cursor(raw)

    async def test_static_status_copy_has_no_dynamic_variable_metadata_or_substitution(self) -> None:
        self.assertTrue(set(MONITOR_TEXT_DEFAULTS).isdisjoint(template_variable_specs()))
        ui = dict(DEFAULT_SETTINGS)
        ui["connection_status_title"] = "{token} {user_id.__class__} <b>وضعیت</b>"
        self.assertEqual(monitor_text(ui, "connection_status_title"), "{token} {user_id.__class__} &lt;b&gt;وضعیت&lt;/b&gt;")
