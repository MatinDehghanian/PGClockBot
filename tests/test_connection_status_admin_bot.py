"""Monitoring callbacks acknowledge promptly, validate IDs and keep FSM navigation safe."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, User

from connection_monitor_support import MonitorDatabaseCase

from app.bot.connection_status_admin_ui import parse_monitor_callback
from app.bot.connection_status_admin_ui import monitor_error
from app.services.connection_monitor_accounts import ACCOUNT_MESSAGES, MonitorAccountError
from app.bot.connection_status_ui import MonitorAdminLabel
from app.services.connection_status_texts import LEGACY_MONITOR_TEXTS, MONITOR_TEXT_DEFAULTS
from app.bot.handlers import connection_status_admin as admin
from app.bot.handlers import connection_status_admin_input as forms
from app.bot.nav_input import CANCEL_CODE_KEY
from app.db.models import BotUser, ConnectionMonitorTarget
from app.services.connection_monitor_admin import MonitorHostPage


class MonitorAdminBotTests(MonitorDatabaseCase):
    async def test_old_default_menu_button_still_opens_settings_without_overriding_custom_labels(self) -> None:
        old_button = self.message.model_copy(update={"text": LEGACY_MONITOR_TEXTS["btn_connection_status_admin"]})
        matcher = MonitorAdminLabel()
        async with self.Session() as session:
            with patch("app.bot.connection_status_ui.get_all_settings", AsyncMock(return_value=MONITOR_TEXT_DEFAULTS)):
                self.assertTrue(await matcher(old_button, session))
            with patch("app.bot.connection_status_ui.get_all_settings", AsyncMock(return_value={"btn_connection_status_admin": "هاست‌ها"})):
                self.assertFalse(await matcher(old_button, session))
                self.assertTrue(await matcher(self.message.model_copy(update={"text": "هاست‌ها"}), session))

    async def test_account_validation_failure_shows_the_actionable_reason(self) -> None:
        with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
            async with self.Session() as session:
                await monitor_error(self.message, session, MonitorAccountError("inactive"))
        self.assertEqual(answer.call_args.args[0], ACCOUNT_MESSAGES["inactive"])

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.message = Message(message_id=100, date=datetime.now(timezone.utc), chat=Chat(id=101, type="private"),
                               from_user=User(id=101, is_bot=False, first_name="Owner"), text="نام عمومی")
        self.storage = MemoryStorage()
        self.state = FSMContext(self.storage, StorageKey(bot_id=1, chat_id=101, user_id=101))
        self.user = BotUser(id=1, telegram_id=101, referral_code="owner", role="admin")
        delete = patch.object(Message, "delete", new_callable=AsyncMock)
        delete.start()
        self.addCleanup(delete.stop)

    async def asyncTearDown(self) -> None:
        await self.storage.close()
        await super().asyncTearDown()

    def callback(self, data: str) -> CallbackQuery:
        return CallbackQuery(id="callback", from_user=self.message.from_user, chat_instance="synthetic", data=data, message=self.message)

    async def test_callback_acknowledges_before_a_slow_catalog_operation(self) -> None:
        with patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer:
            async def picker(*args: object, **kwargs: object) -> MonitorHostPage:
                self.assertEqual(answer.await_count, 1)
                return MonitorHostPage((), None)
            with patch.object(admin, "bot_monitor_access", AsyncMock(return_value=self.access)):
                with patch.object(admin, "active_monitor_hosts", side_effect=picker):
                    with patch.object(admin, "safe_edit_text", new_callable=AsyncMock) as render:
                        async with self.Session() as session:
                            await admin.monitor_admin_callback(self.callback("cma:hosts:0"), session, self.user, self.state)
                        self.assertIn("هاست فعال دیگری", render.call_args.args[1])

    async def test_invalid_callback_never_mutates_settings_or_leaks_input(self) -> None:
        invalid = ("cma:public:-1:1", "cma:item:2147483648", "cma:item:True", "cma:public:10:2",
                   "cma:item:۱۰", "cma:halt:9", "cma:item:1:extra")
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_monitor_callback(raw)
        with patch.object(CallbackQuery, "answer", new_callable=AsyncMock):
            with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
                with patch.object(admin, "_mutate", new_callable=AsyncMock) as mutate:
                    async with self.Session() as session:
                        await admin.monitor_admin_callback(self.callback("cma:item:invalid-secret"), session, self.user, self.state)
                    mutate.assert_not_called()
                    self.assertNotIn("invalid-secret", str(answer.call_args))

    async def test_name_prompt_and_cancel_reopen_without_saving_the_field(self) -> None:
        await self.state.set_state(forms.MonitorInput.public_name)
        await self.state.update_data(**{CANCEL_CODE_KEY: forms.CANCEL_CODE, "monitor_target_id": 10})
        cancel = self.message.model_copy(update={"text": "انصراف"})
        with patch.object(Message, "answer", new_callable=AsyncMock):
            with patch("app.bot.connection_status_admin_ui.bot_monitor_access", AsyncMock(return_value=self.access)):
                with patch.object(forms, "edit_monitor_target", new_callable=AsyncMock) as edit:
                    async with self.Session() as session:
                        await forms.monitor_input(cancel, session, self.user, self.state)
                    edit.assert_not_called()
        self.assertIsNone(await self.state.get_state())

    async def test_field_input_calls_the_scoped_service_and_clears_the_fsm_after_success(self) -> None:
        async with self.Session() as session:
            session.add(ConnectionMonitorTarget(id=10, pg_host_id=41, test_enabled=True, generation="one", endpoint_count=1))
            await session.commit()
        await self.state.set_state(forms.MonitorInput.public_name)
        await self.state.update_data(monitor_target_id=10)
        with patch.object(Message, "answer", new_callable=AsyncMock):
            with patch.object(forms, "bot_monitor_access", AsyncMock(return_value=self.access)):
                with patch.object(forms, "edit_monitor_target", new_callable=AsyncMock) as edit:
                    async with self.Session() as session:
                        await forms.monitor_input(self.message, session, self.user, self.state)
                        self.assertEqual(edit.call_args.kwargs, {"target_id": 10, "field": "public_name", "value": "نام عمومی"})
        self.assertIsNone(await self.state.get_state())

    async def test_private_entry_denial_does_not_read_monitoring_data(self) -> None:
        with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
            with patch.object(admin, "bot_monitor_access", AsyncMock(side_effect=ValueError("دسترسی به مدیریت وضعیت اتصال مجاز نیست."))):
                with patch.object(admin, "show_monitor_home", new_callable=AsyncMock) as show:
                    async with self.Session() as session:
                        await admin.monitor_admin_entry(self.message, session, self.user, self.state)
                    show.assert_not_called()
                    self.assertIn("دسترسی", answer.call_args.args[0])
