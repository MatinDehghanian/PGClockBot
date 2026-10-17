"""Editable menu titles: defaults match the old titles, menus show the setting, editor saves it."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.handlers import screen_editor as ui_module
from app.bot.screen_registry import SCREENS
from app.db.models import ResellerSetting, Setting
from app.services.screen_editor import EditorActor, edit_mode_store
from app.services.screen_titles import (
    SCREEN_TITLE_DEFAULTS,
    screen_heading,
    screen_title,
    title_setting_key,
    validate_screen_title,
)
from app.services.users import DEFAULT_SETTINGS, clear_settings_cache

# What the menus rendered before titles became settings; the defaults must keep them byte-for-byte.
OLD_HEADINGS = {
    "c.services": "📦 <b>سرویس‌های شما</b>",
    "a.home": "🛠 <b>پنل ادمین</b>",
    "a.ops": "🗓 <b>عملیات روزانه</b>",
    "a.people": "👤 <b>افراد</b>",
    "a.product": "📦 <b>محصول و PG</b>",
    "a.marketing": "🎯 <b>بازاریابی</b>",
    "a.system": "🛠 <b>سیستم</b>",
    "a.pg": "🖥 <b>عملیات پاسارگارد</b>",
    "a.loyalty": "⭐ <b>باشگاه مشتریان</b>",
    "a.users": "👥 <b>کاربران بات</b>",
    "a.resellers": "🤝 <b>نمایندگان</b>",
    "a.settings": "⚙️ <b>تنظیمات سریع</b>",
    "a.backup": "💾 <b>بکاپ / ریستور</b>",
    "a.broadcast": "📢 <b>پیام گروهی</b>",
    "a.plans": "💎 <b>پلن‌ها</b>",
    "a.plans.users": "👥 <b>پلن‌های کاربران</b>",
    "a.plans.resellers": "🤝 <b>پلن‌های نمایندگان</b>",
    "r.settings": "⚙️ <b>تنظیمات سریع فروشگاه</b>",
    "r.plans": "💎 <b>پلن‌های فروش</b>",
}
OLD_PLAIN_TITLES = {
    "c.wallet": "👛 کیف پول",
    "c.support": "🎧 پشتیبانی",
    "c.loyalty": "⭐ باشگاه مشتریان",
    "r.home": "🤝 پنل نماینده",
}
OWNER = EditorActor(user_id=7, shop_id=None)
SHOP_A = 501
SHOP_OWNER = EditorActor(user_id=8, shop_id=SHOP_A)


class TitleDefaultTests(unittest.TestCase):
    def test_defaults_render_exactly_the_old_titles(self) -> None:
        for screen_id, heading in OLD_HEADINGS.items():
            with self.subTest(screen=screen_id):
                self.assertEqual(screen_heading({}, screen_id), heading)
                self.assertEqual(screen_heading(dict(DEFAULT_SETTINGS), screen_id), heading)
        for screen_id, title in OLD_PLAIN_TITLES.items():
            with self.subTest(screen=screen_id):
                self.assertEqual(screen_title(dict(DEFAULT_SETTINGS), screen_id), title)

    def test_every_title_belongs_to_a_registered_menu(self) -> None:
        self.assertEqual(set(SCREEN_TITLE_DEFAULTS), set(OLD_HEADINGS) | set(OLD_PLAIN_TITLES))
        self.assertLessEqual(set(SCREEN_TITLE_DEFAULTS), set(SCREENS))

    def test_stored_title_wins_and_blank_falls_back(self) -> None:
        key = title_setting_key("a.ops")
        self.assertEqual(screen_heading({key: "🚀 کارهای امروز"}, "a.ops"), "🚀 <b>کارهای امروز</b>")
        self.assertEqual(screen_heading({key: "کارهای امروز"}, "a.ops"), "<b>کارهای امروز</b>")
        self.assertEqual(screen_heading({key: "   "}, "a.ops"), OLD_HEADINGS["a.ops"])

    def test_heading_escapes_whatever_is_stored(self) -> None:
        key = title_setting_key("a.ops")
        self.assertEqual(screen_heading({key: "<i>x</i>"}, "a.ops"), "<b>&lt;i&gt;x&lt;/i&gt;</b>")

    def test_title_validation(self) -> None:
        self.assertEqual(validate_screen_title("  🚀  کارهای   امروز "), "🚀 کارهای امروز")
        for text in ("", "خط\nدوم", "x" * 65, "<b>bold</b>", "A & B"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_screen_title(text)


class MenuRendersTitleTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_ops_hub_shows_the_stored_title(self) -> None:
        from app.bot.handlers import reply_nav

        ui = dict(DEFAULT_SETTINGS)
        ui[title_setting_key("a.ops")] = "🚀 کارهای امروز"
        with (
            patch.object(reply_nav, "_deny_unless_owner", AsyncMock(return_value=True)),
            patch.object(reply_nav, "get_all_settings", AsyncMock(return_value=ui)),
            patch("app.services.admin_counters.pending_counts", AsyncMock(side_effect=RuntimeError)),
            patch("app.bot.nav_inline.present_nav_panel", AsyncMock()) as present,
        ):
            await reply_nav.open_admin_ops_hub(MagicMock(), MagicMock(), MagicMock(id=1), None)
        self.assertTrue(present.await_args.kwargs["text"].startswith("🚀 <b>کارهای امروز</b>\n"))

    async def test_wallet_home_shows_the_stored_title(self) -> None:
        from app.bot.handlers import reply_nav

        ui = dict(DEFAULT_SETTINGS)
        ui[title_setting_key("c.wallet")] = "💰 حساب من"
        with (
            patch.object(reply_nav, "get_all_settings", AsyncMock(return_value=ui)),
            patch("app.services.wallet.wallet_balance_for_context", AsyncMock(return_value=0)),
            patch("app.bot.nav_inline.present_inline_only", AsyncMock()) as present,
        ):
            await reply_nav.open_wallet_home(MagicMock(), MagicMock(), MagicMock(id=1), None)
        self.assertIn("<b>💰 حساب من</b>", present.await_args.kwargs["text"])

    def test_backup_panel_shows_its_title_once(self) -> None:
        from app.bot.handlers.admin_backup import _hub_text

        text = _hub_text([], dict(DEFAULT_SETTINGS))
        self.assertEqual(text.count("بکاپ / ریستور</b>"), 1)
        self.assertTrue(text.startswith(OLD_HEADINGS["a.backup"]))


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


class TitleEditorFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from app.db import Base
        import app.db.models  # noqa: F401  (registers every table on Base)

        self._tmpdir = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{Path(self._tmpdir.name) / 'titles.db'}")
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

    async def _start_editing(self) -> None:
        await self._owner("ed:a:f1")
        await self._owner("ed:a:m1")
        edit_mode_store.activate(SHOP_OWNER)

    async def _owner_text(self, text: str) -> MagicMock:
        message = _message(text)
        async with self.Session() as session:
            await ui_module.owner_label_text(message, self.state, session, MagicMock(id=OWNER.user_id))
        return message

    async def _platform(self, key: str) -> str | None:
        async with self.Session() as session:
            return await session.scalar(select(Setting.value).where(Setting.key == key))

    async def _shop_value(self, key: str) -> str | None:
        async with self.Session() as session:
            return await session.scalar(
                select(ResellerSetting.value).where(ResellerSetting.reseller_user_id == SHOP_A, ResellerSetting.key == key)
            )

    async def test_panel_offers_the_title_first(self) -> None:
        await self._start_editing()
        callback = await self._owner("ed:a:o:a.ops")
        markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "ed:a:n:a.ops")
        self.assertIn("🗓 عملیات روزانه", markup.inline_keyboard[0][0].text)

    async def test_owner_changes_a_title_and_returns_to_the_menu(self) -> None:
        await self._start_editing()
        edit_mode_store.activate(OWNER, now=time.monotonic() - 25 * 60)
        await self._owner("ed:a:n:a.ops")
        message = await self._owner_text("🚀 کارهای امروز")
        self.assertEqual(await self._platform(title_setting_key("a.ops")), "🚀 کارهای امروز")
        self.assertEqual(edit_mode_store.minutes_left(OWNER), 30)
        self.assertIsNone(await self.state.get_state())
        markup = message.answer.await_args.kwargs["reply_markup"]
        self.assertIn("🚀 کارهای امروز", markup.inline_keyboard[0][0].text)
        self.assertEqual(markup.inline_keyboard[-1][0].callback_data, "nv:adm:ops")

    async def test_unsafe_title_is_refused_and_input_stays_open(self) -> None:
        await self._start_editing()
        await self._owner("ed:a:n:a.ops")
        await self._owner_text("<b>x</b>")
        self.assertIsNone(await self._platform(title_setting_key("a.ops")))
        self.assertEqual(await self.state.get_state(), ui_module.EditorStates.owner_label.state)

    async def test_button_edit_after_a_title_edit_saves_a_button_label(self) -> None:
        await self._start_editing()
        await self._owner("ed:a:n:a.ops")
        await self._owner_text("🚀 کارهای امروز")
        await self._owner("ed:a:t:c.wallet:0")
        await self._owner_text("💳 شارژ سریع")
        self.assertEqual(await self._platform("btn_wallet_topup"), "💳 شارژ سریع")
        self.assertIsNone(await self._platform(title_setting_key("c.wallet")))

    async def test_shop_owner_titles_stay_in_their_shop(self) -> None:
        await self._start_editing()
        with patch.object(ui_module, "shop_settings_shop_id", AsyncMock(return_value=SHOP_A)):
            async with self.Session() as session:
                await ui_module.shop_editor(
                    _callback("ed:r:n:c.wallet"), session, MagicMock(id=SHOP_OWNER.user_id), self.state,
                    is_reseller_bot=True, reseller_owner_id=SHOP_A,
                )
                await ui_module.shop_label_text(
                    _message("💰 حساب من"), self.state, session, MagicMock(id=SHOP_OWNER.user_id),
                    is_reseller_bot=True, reseller_owner_id=SHOP_A,
                )
                refused = _callback("ed:r:n:a.ops")
                await ui_module.shop_editor(
                    refused, session, MagicMock(id=SHOP_OWNER.user_id), self.state,
                    is_reseller_bot=True, reseller_owner_id=SHOP_A,
                )
        self.assertEqual(await self._shop_value(title_setting_key("c.wallet")), "💰 حساب من")
        self.assertIsNone(await self._platform(title_setting_key("c.wallet")))
        self.assertTrue(refused.answer.await_args.kwargs.get("show_alert"))


if __name__ == "__main__":
    unittest.main()
