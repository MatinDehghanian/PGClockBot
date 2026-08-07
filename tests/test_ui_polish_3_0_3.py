"""UI polish 3.0.3 — static settings actions, bot lists, RTL money, cancel prompts."""

from __future__ import annotations

import unittest
from pathlib import Path

from aiogram.types import InlineKeyboardButton

from app.bot.keyboards import chunk_buttons
from app.services.formatting import format_message, format_toman, rtl_text


ROOT = Path(__file__).resolve().parents[1]


class StickyActionsDesktopTests(unittest.TestCase):
    def test_settings_actions_are_not_sticky(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        block = css.split(".sticky-actions {", 1)[1].split("}", 1)[0]
        self.assertNotIn("position: sticky", block)
        self.assertNotIn("position: fixed", block)


class PlanListTextTests(unittest.TestCase):
    def test_admin_plan_line_no_short_units(self):
        src = (ROOT / "app/bot/handlers/admin.py").read_text(encoding="utf-8")
        self.assertNotIn("ر / {gb}", src)
        self.assertNotIn("ر / ", src)
        self.assertIn("def _plan_line", src)


class RtlMoneyTests(unittest.TestCase):
    def test_format_toman_has_rlm(self):
        s = format_toman(150000, "تومان")
        self.assertTrue(s.startswith("\u200f"))
        self.assertIn("تومان", s)

    def test_format_message_rtl_lines(self):
        msg = format_message("عنوان", "قیمت:\n150")
        self.assertIn("\u200f", msg)
        self.assertIn("━━━━━━━━━━━━", msg)
        self.assertTrue(rtl_text("abc").startswith("\u200f"))


class TwoColumnListTests(unittest.TestCase):
    def test_chunk_buttons_packs_two_cols(self):
        btns = [InlineKeyboardButton(text=str(i), callback_data=f"x:{i}") for i in range(5)]
        rows = chunk_buttons(btns, cols=2)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(rows[0]), 2)
        self.assertEqual(len(rows[1]), 2)
        self.assertEqual(len(rows[2]), 1)

    def test_list_keyboards_use_chunk(self):
        kb_src = (ROOT / "app/bot/keyboards.py").read_text(encoding="utf-8")
        self.assertIn("chunk_buttons(flat, cols=2)", kb_src)
        res_src = (ROOT / "app/bot/handlers/reseller.py").read_text(encoding="utf-8")
        self.assertIn("chunk_buttons(buttons, cols=2)", res_src)
        pg_src = (ROOT / "app/bot/handlers/admin_pg_users.py").read_text(encoding="utf-8")
        self.assertIn("chunk_buttons(buttons, cols=2)", pg_src)


class CancelReplyPromptTests(unittest.TestCase):
    def test_fsm_steps_reassert_cancel_keyboard(self):
        admin = (ROOT / "app/bot/handlers/admin.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(admin.count("reply_markup=kb.cancel_reply()"), 4)
        support = (ROOT / "app/bot/handlers/support.py").read_text(encoding="utf-8")
        self.assertIn('await message.answer("متن پیام را بنویسید:", reply_markup=kb.cancel_reply())', support)
        backup = (ROOT / "app/bot/handlers/admin_backup.py").read_text(encoding="utf-8")
        self.assertIn("reply_markup=kb.cancel_reply()", backup)


if __name__ == "__main__":
    unittest.main()
