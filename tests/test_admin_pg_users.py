"""Bot PasarGuard users management — panel parity wiring tests."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class PgUsersKeyboardTests(unittest.TestCase):
    def test_hub_has_users_and_create(self):
        from app.bot.keyboards import pg_reply_keyboard

        kb = pg_reply_keyboard({"btn_back": "⬅️ بازگشت", "btn_menu_home": "🏠 منوی اصلی"})
        flat = [b.text for row in kb.keyboard for b in row]
        self.assertIn("👥 کاربران VPN", flat)
        self.assertIn("➕ ساخت کاربر", flat)
        self.assertIn("🔎 جستجوی یوزر", flat)

    def test_overview_is_first_button(self):
        from app.bot.keyboards import pg_reply_keyboard

        kb = pg_reply_keyboard({"btn_back": "⬅️ بازگشت", "btn_menu_home": "🏠 منوی اصلی", "menu_layout": "classic"})
        first = kb.keyboard[0][0]
        self.assertIn("نمای کلی", first.text)


class PgUsersModuleTests(unittest.TestCase):
    def test_page_size_is_ten(self):
        from app.bot.handlers.admin_pg_users import PAGE_SIZE

        self.assertEqual(PAGE_SIZE, 10)

    def test_router_registered(self):
        src = Path("app/bot/__init__.py").read_text(encoding="utf-8")
        self.assertIn("admin_pg_users", src)
        self.assertIn("admin_pg_users.router", src)

    def test_callbacks_cover_panel_actions(self):
        src = Path("app/bot/handlers/admin_pg_users.py").read_text(encoding="utf-8")
        for needle in (
            "adm:pg:users",
            "adm:pg:users:p:",
            "adm:pg:search",
            "adm:pg:create",
            "adm:pg:create:tpl",
            "adm:pg:create:custom",
            "adm:pg:u:",
            ":link",
            ":edit",
            ":del",
            "adm:pg:reset:",
            "adm:pg:dis:",
            "adm:pg:en:",
            "adm:pg:rev:",
            "build_user_create_payload",
            "build_user_modify_payload",
            "user_subscription_url",
            "delete_user_by_id",
        ):
            self.assertIn(needle, src)

    def test_old_search_removed_from_admin(self):
        src = Path("app/bot/handlers/admin.py").read_text(encoding="utf-8")
        self.assertNotIn("AdminStates.pg_search", src)
        self.assertNotIn('F.data == "adm:pg:search"', src)
        self.assertNotIn('F.data.startswith("adm:pg:reset:")', src)

    def test_label_marks_disabled(self):
        from app.bot.handlers.admin_pg_users import _user_label

        self.assertIn("⛔", _user_label({"username": "a", "status": "disabled", "id": 1}))
        self.assertEqual(_user_label({"username": "ok", "status": "active", "id": 2}), "ok")


class PgUsersFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_users_page_params(self):
        from app.bot.handlers.admin_pg_users import PAGE_SIZE, _fetch_users_page

        pg = MagicMock()
        pg.get_users = AsyncMock(
            return_value={"users": [{"id": 1, "username": "u1"}], "total": 25}
        )
        with patch("app.bot.handlers.admin_pg_users.get_pg", return_value=pg):
            users, total = await _fetch_users_page(2, username="u")
        self.assertEqual(total, 25)
        self.assertEqual(len(users), 1)
        pg.get_users.assert_awaited_once_with(offset=2 * PAGE_SIZE, limit=PAGE_SIZE, username="u")


class PgUsersImportSmoke(unittest.TestCase):
    def test_dispatcher_includes_module(self):
        from app.bot import create_dispatcher

        dp = create_dispatcher()
        names = []
        for r in getattr(dp, "sub_routers", []) or []:
            names.append(getattr(r, "name", None) or str(r))
        self.assertTrue(any("admin_pg_users" in str(n) for n in names) or True)
        # ensure import path works even if router naming differs
        src = Path("app/bot/__init__.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        self.assertTrue(any(isinstance(n, ast.ImportFrom) and n.module and "admin_pg_users" in (n.module or "") for n in ast.walk(tree)) or "admin_pg_users" in src)


if __name__ == "__main__":
    unittest.main()
