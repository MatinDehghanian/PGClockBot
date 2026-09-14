"""Pre-v10 delete UX restored: no type-to-confirm on VPN/service deletes."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SimpleDeleteConfirmRestoredTests(unittest.TestCase):
    def test_panel_js_still_has_phrase_capability(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("confirmPhrase", js)
        self.assertIn("data-confirm-phrase", js)

    def test_pg_users_delete_is_simple_confirm(self):
        html = (ROOT / "app/web/templates/pg_users.html").read_text(encoding="utf-8")
        self.assertNotIn("data-confirm-phrase", html)
        self.assertNotIn("'phrase': 'حذف'", html)
        self.assertIn("/pg/users/{{ uid }}/delete", html)
        self.assertIn("data-confirm=", html)

    def test_service_delete_is_simple_confirm(self):
        html = (ROOT / "app/web/templates/_user_edit_body.html").read_text(encoding="utf-8")
        self.assertRegex(html, r"/services/\{\{\s*s\.service\.id\s*\}\}/delete")
        self.assertNotIn("data-confirm-phrase", html)

    def test_macros_may_still_expose_phrase_attrs(self):
        macros = (ROOT / "app/web/templates/macros.html").read_text(encoding="utf-8")
        self.assertIn("data-bulk-confirm-phrase", macros)

    def test_server_does_not_enforce_phrase(self):
        pg = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        users = (ROOT / "app/api/user_pages.py").read_text(encoding="utf-8")
        bulk = (ROOT / "app/api/bulk_pages.py").read_text(encoding="utf-8")
        self.assertNotIn("confirm_phrase", pg)
        self.assertNotIn("نام کاربری را دقیق تایپ کنید", pg)
        self.assertNotIn("confirm_phrase", users)
        self.assertNotIn("confirm_phrase", bulk)
        self.assertNotIn('phrase != "حذف"', bulk)

    def test_bot_delete_ask_is_simple_yes_cancel(self):
        bot = (ROOT / "app/bot/handlers/admin_pg_users.py").read_text(encoding="utf-8")
        m = re.search(r"async def (pg_user_del\w*)\(", bot)
        self.assertIsNotNone(m)
        # Prefer ask handler
        ask = None
        for name in re.findall(r"async def (pg_user_del\w*)\(", bot):
            if "ask" in name:
                ask = name
                break
        self.assertIsNotNone(ask)
        start = bot.find(f"async def {ask}")
        # next async def after ask
        m2 = re.search(r"\nasync def ", bot[start + 10 :])
        end = start + 10 + m2.start() if m2 else len(bot)
        block = bot[start:end]
        self.assertIn("بله، حذف شود", block)
        self.assertIn("انصراف", block)
        self.assertNotIn("فقط غیرفعال", block)
        self.assertNotIn("حذف دائمی", block)

    def test_pg_users_have_no_reason_or_phrase_gate(self):
        html = (ROOT / "app/web/templates/pg_users.html").read_text(encoding="utf-8")
        self.assertNotIn("data-confirm-reason", html)
        self.assertNotIn("data-confirm-phrase", html)


if __name__ == "__main__":
    unittest.main()
