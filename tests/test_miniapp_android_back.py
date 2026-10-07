"""Android/system back — Mini App BackButton + chat reply-keyboard persistence.

Two separate Telegram behaviors commonly reported as «بک اندروید کار نمی‌کند»:

1. Mini App: OS back only navigates in-app when ``WebApp.BackButton`` is shown.
2. Bot chat: with ``ReplyKeyboardMarkup.is_persistent=True``, Android often
   cannot dismiss the custom keyboard, so back never reaches the dialog list.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/web/static/miniapp.js").read_text(encoding="utf-8")


class ReplyKeyboardAndroidBackTests(unittest.TestCase):
    def test_reply_markup_not_force_persistent(self):
        from app.bot.reply_keyboards import main_reply_keyboard, shop_reply_keyboard

        ui = {"btn_menu_home": "🏠 منوی اصلی", "btn_back": "⬅️ بازگشت", "btn_shop": "خرید"}
        main = main_reply_keyboard("user", ui=ui)
        shop = shop_reply_keyboard(ui)
        self.assertFalse(main.is_persistent)
        self.assertFalse(shop.is_persistent)
        src = (ROOT / "app/bot/reply_keyboards.py").read_text(encoding="utf-8")
        block = src.split("def _reply_markup(")[1].split("def _reply_user_entries(")[0]
        self.assertIn("is_persistent=False", block)
        self.assertIn("Android", block)


class MiniAppBackButtonTests(unittest.TestCase):
    def test_binds_telegram_back_button(self):
        self.assertIn("function bindTelegramBackButton(", JS)
        self.assertIn("function syncTelegramBackButton(", JS)
        self.assertIn("function onTelegramBack(", JS)
        self.assertIn("tg.BackButton.show()", JS)
        self.assertIn("tg.BackButton.hide()", JS)
        self.assertIn("tg.BackButton.onClick(", JS)
        self.assertIn("backButtonClicked", JS)
        self.assertIn("bindTelegramBackButton()", JS)

    def test_back_closes_overlays_then_returns_home(self):
        self.assertIn("function closeOpenOverlays(", JS)
        self.assertIn("function hasOpenOverlay(", JS)
        self.assertIn("function homeViewId(", JS)
        # Handler priority: overlay → home view
        on_back = JS.split("function onTelegramBack(")[1].split("function bindTelegramBackButton(")[0]
        self.assertLess(
            on_back.find("closeOpenOverlays()"),
            on_back.find("homeViewId()"),
        )
        self.assertIn("setView(homeViewId())", on_back)

    def test_set_view_and_overlays_sync_back_visibility(self):
        set_view = JS.split("function setView(")[1].split("function openPanelPath(")[0]
        self.assertIn("syncTelegramBackButton()", set_view)
        self.assertIn("closeOpenOverlays()", set_view)
        show_qr = JS.split("async function showQr(")[1].split("function showRenew(")[0]
        self.assertIn("syncTelegramBackButton()", show_qr)
        show_renew = JS.split("function showRenew(")[1].split("async function doBuy(")[0]
        self.assertIn("syncTelegramBackButton()", show_renew)

    def test_documents_chat_bot_limitation(self):
        # Regression guard: keep the rationale so future edits don't drop the API.
        self.assertIn("Chat bots cannot intercept hardware back", JS)
        self.assertIn("BackButton is visible", JS)


if __name__ == "__main__":
    unittest.main()
