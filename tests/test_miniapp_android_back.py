"""Android/system back — Mini App BackButton + chat reply-keyboard persistence.

Two separate Telegram behaviors commonly reported as «بک اندروید کار نمی‌کند»:

1. Mini App: OS back only navigates in-app when ``WebApp.BackButton`` is shown
   (behavior covered by ``tests/miniapp_app.test.cjs``).
2. Bot chat: with ``ReplyKeyboardMarkup.is_persistent=True``, Android often
   cannot dismiss the custom keyboard, so back never reaches the dialog list.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
