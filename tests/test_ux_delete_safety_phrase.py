"""Phase 4 — UX delete safety: type-to-confirm for irreversible VPN deletes."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TypeToConfirmPanelJsTests(unittest.TestCase):
    def test_panel_js_supports_confirm_phrase(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("confirmPhrase", js)
        self.assertIn("data-confirm-phrase", js)
        self.assertIn("renderPhraseField", js)
        self.assertIn("applyPhrase", js)
        self.assertIn("data-bulk-confirm-phrase", js)

    def test_pg_users_delete_requires_phrase(self):
        html = (ROOT / "app/web/templates/pg_users.html").read_text(encoding="utf-8")
        self.assertIn("data-confirm-phrase=", html)
        self.assertIn("حذف دائمی", html)
        self.assertIn("غیرفعال", html)
        # Bulk delete asks operator to type «حذف»
        self.assertIn("'phrase': 'حذف'", html)

    def test_service_delete_requires_phrase(self):
        html = (ROOT / "app/web/templates/_user_edit_body.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("/services/{{ s.service.id }}/delete", html)
        self.assertIn("data-confirm-phrase=", html)
        self.assertIn("data-confirm-phrase-name=\"confirm_phrase\"", html)

    def test_macros_bulk_phrase_attrs(self):
        macros = (ROOT / "app/web/templates/macros.html").read_text(encoding="utf-8")
        self.assertIn("data-bulk-confirm-phrase", macros)

    def test_server_enforces_phrase_on_pg_and_service_delete(self):
        pg = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        users = (ROOT / "app/api/user_pages.py").read_text(encoding="utf-8")
        bulk = (ROOT / "app/api/bulk_pages.py").read_text(encoding="utf-8")
        self.assertIn("confirm_phrase", pg)
        self.assertIn("نام کاربری را دقیق تایپ کنید", pg)
        self.assertIn("confirm_phrase", users)
        self.assertIn("confirm_phrase", bulk)
        self.assertIn('phrase != "حذف"', bulk)

    def test_bot_delete_ask_prefers_disable(self):
        bot = (ROOT / "app/bot/handlers/admin_pg_users.py").read_text(encoding="utf-8")
        block = bot[
            bot.find("async def pg_user_del_ask") : bot.find("async def pg_user_del\n")
        ]
        self.assertIn("فقط غیرفعال", block)
        self.assertIn("adm:pg:dis:", block)
        self.assertIn("حذف دائمی", block)
        self.assertIn("برگشت‌ناپذیر", block)

    def test_reason_allowlist_still_excludes_pg_users_reason(self):
        """PG VPN deletes use phrase, not free-text reason."""
        html = (ROOT / "app/web/templates/pg_users.html").read_text(encoding="utf-8")
        self.assertNotIn("data-confirm-reason", html)
        self.assertIn("data-confirm-phrase", html)


if __name__ == "__main__":
    unittest.main()
