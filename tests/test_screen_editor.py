"""In-menu screen editor: edit mode, the edit row, permissions, shop isolation and the flow."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot import menu_nav as nav
from app.bot.edit_mode import EDIT_ROW_TEXT, EditModeMiddleware, editing_as
from app.bot.handlers import screen_editor as ui_module
from app.bot.screen_registry import SCREENS, ScreenContext, screen_buttons
from app.db.models import ResellerSetting, Setting
from app.services.screen_editor import (
    SCREEN_EDITOR_SETTING,
    EditModeStore,
    EditorActor,
    can_edit_label,
    edit_mode_store,
    validate_button_label,
)
from app.services.users import DEFAULT_SETTINGS, clear_settings_cache
from tests.test_bot_ui_keyboard_snapshots import default_ui, sample_reseller_profile

OWNER = EditorActor(user_id=7, shop_id=None)
SHOP_A = 501
SHOP_B = 502
SHOP_OWNER = EditorActor(user_id=8, shop_id=SHOP_A)


class EditModeStoreTests(unittest.TestCase):
    def test_switch_expires_after_its_window(self) -> None:
        store = EditModeStore(minutes=30)
        store.activate(OWNER, now=1000.0)
        self.assertTrue(store.is_active(OWNER, now=1000.0 + 29 * 60))
        self.assertEqual(store.minutes_left(OWNER, now=1000.0 + 10 * 60), 20)
        self.assertFalse(store.is_active(OWNER, now=1000.0 + 30 * 60))

    def test_switch_is_per_person_and_per_shop(self) -> None:
        store = EditModeStore()
        store.activate(SHOP_OWNER, now=0.0)
        self.assertFalse(store.is_active(EditorActor(user_id=8, shop_id=None), now=1.0))
        self.assertFalse(store.is_active(EditorActor(user_id=8, shop_id=SHOP_B), now=1.0))
        store.deactivate(SHOP_OWNER)
        self.assertFalse(store.is_active(SHOP_OWNER, now=1.0))

    def test_store_never_grows_past_its_capacity(self) -> None:
        store = EditModeStore(capacity=3)
        for user_id in range(10):
            store.activate(EditorActor(user_id=user_id, shop_id=None), now=float(user_id))
        active = [u for u in range(10) if store.is_active(EditorActor(user_id=u, shop_id=None), now=10.0)]
        self.assertEqual(active, [7, 8, 9])


class LabelRuleTests(unittest.TestCase):
    def test_label_validation(self) -> None:
        self.assertEqual(validate_button_label("  کیف   پول  ", other_labels=[], reserved=[]), "کیف پول")
        for text, others, reserved in (
            ("", [], []),
            ("خط اول\nخط دوم", [], []),
            ("x" * 65, [], []),
            ("انصراف", [], ["انصراف"]),
            ("🟢 خرید", ["🟢 خرید"], []),
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_button_label(text, other_labels=others, reserved=reserved)

    def test_owner_and_shop_label_permissions(self) -> None:
        self.assertTrue(can_edit_label(OWNER, "btn_admin"))
        self.assertFalse(can_edit_label(SHOP_OWNER, "btn_admin"))
        self.assertTrue(can_edit_label(SHOP_OWNER, "btn_wallet"))
        self.assertFalse(can_edit_label(OWNER, "welcome_text"))
        self.assertFalse(can_edit_label(OWNER, None))


class EditRowTests(unittest.TestCase):
    def _last_row(self, screen_id: str, actor: EditorActor | None) -> list:
        ctx = ScreenContext(ui=default_ui(), profile=sample_reseller_profile())
        with editing_as(actor):
            markup = SCREENS[screen_id].build(ctx)
        if not isinstance(markup, InlineKeyboardMarkup):
            return []
        return markup.inline_keyboard[-1]

    def test_every_inline_screen_offers_its_own_editor_to_allowed_people(self) -> None:
        for screen_id, spec in SCREENS.items():
            if screen_id == "c.main":
                continue  # reply keyboard; reached from «✏️ ویرایش منوی اصلی»
            for actor, code in ((OWNER, "a"), (SHOP_OWNER, "r")):
                row = self._last_row(screen_id, actor)
                allowed = spec.audience.value in actor.audiences
                with self.subTest(screen=screen_id, actor=code):
                    if allowed:
                        self.assertEqual(row[0].text, EDIT_ROW_TEXT)
                        self.assertEqual(row[0].callback_data, f"ed:{code}:o:{screen_id}")
                    else:
                        self.assertNotEqual(row[0].text, EDIT_ROW_TEXT)

    def test_no_edit_row_without_an_active_editor(self) -> None:
        for screen_id in SCREENS:
            for button in self._last_row(screen_id, None):
                self.assertNotEqual(button.text, EDIT_ROW_TEXT)

    def test_editor_lists_buttons_without_its_own_row(self) -> None:
        with editing_as(OWNER):
            texts = [b.text for b in screen_buttons("c.wallet", ScreenContext(ui=default_ui()))]
        self.assertNotIn(EDIT_ROW_TEXT, texts)


class ReopenCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_screen_returns_through_a_registered_handler(self) -> None:
        from app.bot import create_dispatcher

        dispatcher = create_dispatcher()
        user = User(id=1, is_bot=False, first_name="t")
        for screen_id, spec in SCREENS.items():
            event = CallbackQuery(id="1", from_user=user, chat_instance="1", data=spec.reopen_callback)
            matched = False
            for router in dispatcher.chain_tail:
                for handler in router.callback_query.handlers:
                    try:
                        ok, _ = await handler.check(event)
                    except Exception:  # filters that need runtime data cannot match a bare event
                        ok = False
                    if ok:
                        matched = True
                        break
                if matched:
                    break
            with self.subTest(screen=screen_id, callback=spec.reopen_callback):
                self.assertTrue(matched)


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def _seen_editor(self, *, active: bool, feature_on: bool, preview: bool) -> EditorActor | None:
        from app.bot.edit_mode import active_editor

        state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))
        if preview:
            await state.update_data({nav.USER_PREVIEW_ACTIVE: True})
        actor = EditorActor(user_id=99, shop_id=None)
        if active:
            edit_mode_store.activate(actor)
        seen: list[EditorActor | None] = []

        async def handler(_event, _data):
            seen.append(active_editor())

        data = {"db_user": MagicMock(id=99), "is_reseller_bot": False, "session": MagicMock(), "state": state}
        try:
            with patch("app.bot.edit_mode.is_editor_enabled", AsyncMock(return_value=feature_on)):
                await EditModeMiddleware()(handler, MagicMock(), data)
        finally:
            edit_mode_store.deactivate(actor)
        return seen[0]

    async def test_editor_is_published_only_when_switched_on_enabled_and_not_previewing(self) -> None:
        self.assertEqual(await self._seen_editor(active=True, feature_on=True, preview=False), EditorActor(99, None))
        self.assertIsNone(await self._seen_editor(active=False, feature_on=True, preview=False))
        self.assertIsNone(await self._seen_editor(active=True, feature_on=False, preview=False))
        self.assertIsNone(await self._seen_editor(active=True, feature_on=True, preview=True))


def _callback(data: str) -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    return callback


def _message(text: str) -> MagicMock:
    message = MagicMock()
    message.text = text
    message.entities = None
    message.answer = AsyncMock()
    return message


class EditorFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from app.db import Base
        import app.db.models  # noqa: F401  (registers every table on Base)

        self._tmpdir = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{Path(self._tmpdir.name) / 'editor.db'}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)
        self.state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))
        clear_settings_cache()

    async def asyncTearDown(self) -> None:
        edit_mode_store.deactivate(OWNER)
        edit_mode_store.deactivate(SHOP_OWNER)
        clear_settings_cache()
        await self.engine.dispose()
        self._tmpdir.cleanup()

    async def _owner(self, data: str) -> MagicMock:
        callback = _callback(data)
        async with self.Session() as session:
            await ui_module.owner_editor(callback, session, MagicMock(id=OWNER.user_id), self.state)
        return callback

    async def _shop(self, data: str, *, on_shop_bot: bool = True, has_access: bool = True) -> MagicMock:
        callback = _callback(data)
        with patch.object(ui_module, "shop_settings_shop_id", AsyncMock(return_value=SHOP_A if has_access else None)):
            async with self.Session() as session:
                await ui_module.shop_editor(
                    callback, session, MagicMock(id=SHOP_OWNER.user_id), self.state,
                    is_reseller_bot=on_shop_bot, reseller_owner_id=SHOP_A,
                )
        return callback

    async def _platform(self, key: str) -> str | None:
        async with self.Session() as session:
            return await session.scalar(select(Setting.value).where(Setting.key == key))

    async def _shop_value(self, shop_id: int, key: str) -> str | None:
        async with self.Session() as session:
            return await session.scalar(
                select(ResellerSetting.value).where(ResellerSetting.reseller_user_id == shop_id, ResellerSetting.key == key)
            )

    def _index(self, screen_id: str, label_key: str) -> int:
        buttons = screen_buttons(screen_id, ScreenContext(ui=dict(DEFAULT_SETTINGS), profile=sample_reseller_profile()))
        return next(i for i, b in enumerate(buttons) if b.label_key == label_key)

    def _alerted(self, callback: MagicMock) -> bool:
        return bool(callback.answer.await_args and callback.answer.await_args.kwargs.get("show_alert"))

    async def test_edit_mode_needs_the_feature_switch(self) -> None:
        self.assertTrue(self._alerted(await self._owner("ed:a:m1")))
        self.assertFalse(edit_mode_store.is_active(OWNER))
        await self._owner("ed:a:f1")
        self.assertEqual(await self._platform(SCREEN_EDITOR_SETTING), "1")
        await self._owner("ed:a:m1")
        self.assertTrue(edit_mode_store.is_active(OWNER))
        await self._owner("ed:a:f0")
        self.assertFalse(edit_mode_store.is_active(OWNER))

    async def test_owner_changes_a_color_and_a_label_from_the_menu(self) -> None:
        await self._owner("ed:a:f1")
        index = self._index("c.wallet", "btn_wallet_topup")
        await self._owner(f"ed:a:c:c.wallet:{index}:d")
        self.assertEqual(await self._platform("btn_style_wallet_topup"), "danger")
        await self._owner(f"ed:a:t:c.wallet:{index}")
        self.assertEqual(await self.state.get_state(), ui_module.EditorStates.owner_label.state)
        message = _message("💳 شارژ")
        async with self.Session() as session:
            await ui_module.owner_label_text(message, self.state, session, MagicMock(id=OWNER.user_id))
        self.assertEqual(await self._platform("btn_wallet_topup"), "💳 شارژ")
        self.assertIsNone(await self.state.get_state())
        markup = message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "nv:w:home")

    async def test_label_that_repeats_another_button_is_refused(self) -> None:
        await self._owner("ed:a:f1")
        index = self._index("c.wallet", "btn_wallet_topup")
        await self._owner(f"ed:a:t:c.wallet:{index}")
        other = screen_buttons("c.wallet", ScreenContext(ui=dict(DEFAULT_SETTINGS)))[index + 1].text
        message = _message(other)
        async with self.Session() as session:
            await ui_module.owner_label_text(message, self.state, session, MagicMock(id=OWNER.user_id))
        self.assertIsNone(await self._platform("btn_wallet_topup"))
        self.assertEqual(await self.state.get_state(), ui_module.EditorStates.owner_label.state)

    async def test_cancel_leaves_the_label_unchanged(self) -> None:
        await self._owner("ed:a:f1")
        await self._owner(f"ed:a:t:c.wallet:{self._index('c.wallet', 'btn_wallet_topup')}")
        async with self.Session() as session:
            await ui_module.owner_label_text(_message("انصراف"), self.state, session, MagicMock(id=OWNER.user_id))
        self.assertIsNone(await self._platform("btn_wallet_topup"))
        self.assertIsNone(await self.state.get_state())

    async def test_shop_owner_edits_only_their_own_shop(self) -> None:
        await self._owner("ed:a:f1")
        index = self._index("c.wallet", "btn_wallet_topup")
        await self._shop(f"ed:r:c:c.wallet:{index}:d")
        await self._shop(f"ed:r:t:c.wallet:{index}")
        async with self.Session() as session:
            with patch.object(ui_module, "shop_settings_shop_id", AsyncMock(return_value=SHOP_A)):
                await ui_module.shop_label_text(
                    _message("💳 شارژ"), self.state, session, MagicMock(id=SHOP_OWNER.user_id),
                    is_reseller_bot=True, reseller_owner_id=SHOP_A,
                )
        self.assertEqual(await self._shop_value(SHOP_A, "btn_style_wallet_topup"), "danger")
        self.assertEqual(await self._shop_value(SHOP_A, "btn_wallet_topup"), "💳 شارژ")
        self.assertIsNone(await self._shop_value(SHOP_B, "btn_wallet_topup"))
        self.assertIsNone(await self._platform("btn_wallet_topup"))
        self.assertIsNone(await self._platform("btn_style_wallet_topup"))

    async def test_shop_owner_cannot_open_admin_menus_or_work_from_the_main_bot(self) -> None:
        await self._owner("ed:a:f1")
        self.assertTrue(self._alerted(await self._shop("ed:r:o:a.home")))
        self.assertTrue(self._alerted(await self._shop("ed:r:h", on_shop_bot=False)))
        self.assertTrue(self._alerted(await self._shop("ed:r:h", has_access=False)))
        self.assertTrue(self._alerted(await self._shop("ed:r:f1")))
        self.assertEqual(await self._platform(SCREEN_EDITOR_SETTING), "1")

    async def test_forged_or_stale_button_numbers_are_refused(self) -> None:
        await self._owner("ed:a:f1")
        for data in ("ed:a:c:c.wallet:99:d", "ed:a:t:c.wallet:-1", "ed:a:c:c.wallet:0:z"):
            with self.subTest(data=data):
                self.assertTrue(self._alerted(await self._owner(data)))
        self.assertIsNone(await self._platform("btn_style_wallet_topup"))

    async def test_malformed_callbacks_are_rejected(self) -> None:
        for data in ("ed:x:h", "ed:a:o:no.such", "ed:a:b:c.wallet:one", "ed:a:c:c.wallet:0", "other", None):
            with self.subTest(data=data):
                self.assertIsNone(ui_module.parse_request(data))


class EntryPointTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_opens_edit_mode_from_the_admin_home(self) -> None:
        from app.bot.nav_inline import admin_groups_hub_keyboard

        data = [b.callback_data for row in admin_groups_hub_keyboard(default_ui()).inline_keyboard for b in row]
        self.assertIn("ed:a:h", data)
        _text, markup = ui_module.switches_view(OWNER, feature_on=True, minutes_left=0)
        self.assertEqual(markup.inline_keyboard[-1][0].callback_data, "nv:adm:home")

    async def _shop_menu_section_data(self, *, feature_on: bool) -> list[str]:
        from app.bot.handlers import reseller_settings

        callback = _callback("res:st:sec:menu")
        with patch.object(reseller_settings, "is_editor_enabled", AsyncMock(return_value=feature_on)):
            await reseller_settings._render_section(callback, MagicMock(), "menu", SHOP_A)
        markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
        return [b.callback_data for row in markup.inline_keyboard for b in row]

    async def test_shop_owner_sees_the_entry_only_while_the_feature_is_on(self) -> None:
        self.assertIn("ed:r:h", await self._shop_menu_section_data(feature_on=True))
        self.assertNotIn("ed:r:h", await self._shop_menu_section_data(feature_on=False))

    async def test_owner_settings_no_longer_carry_the_entry(self) -> None:
        from app.bot.handlers import admin_settings

        callback = _callback("adm:st:sec:menu")
        await admin_settings._render_section(callback, MagicMock(), "menu")
        markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
        self.assertNotIn("ed:a:h", [b.callback_data for row in markup.inline_keyboard for b in row])

    async def test_admin_home_with_the_entry_is_shown_to_the_owner_only(self) -> None:
        from app.bot.handlers import reply_nav

        message = MagicMock()
        message.answer = AsyncMock()
        with (
            patch("app.bot.auth.is_bot_owner_principal", AsyncMock(return_value=False)),
            patch("app.bot.nav_inline.present_nav_panel", AsyncMock()) as present,
        ):
            await reply_nav.open_admin_home(message, MagicMock(), MagicMock(id=5))
        present.assert_not_awaited()

    async def test_settings_flow_shortcut_never_skips_the_owner_check_for_editors(self) -> None:
        from app.bot.auth import bot_admin_settings_in_flow

        state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))
        await state.update_data({nav.NAV_LEVEL: nav.NAV_ADMIN_SETTINGS})
        await state.set_state(ui_module.EditorStates.owner_label)
        for data in ("ed:a:h", "ed:a:f1", "bcl:a:g", "bcl:a:s:0:wallet_topup:d"):
            with self.subTest(data=data):
                self.assertFalse(await bot_admin_settings_in_flow(MagicMock(data=data), {"state": state}))
        self.assertFalse(await bot_admin_settings_in_flow(MagicMock(spec=[]), {"state": state}))


if __name__ == "__main__":
    unittest.main()
