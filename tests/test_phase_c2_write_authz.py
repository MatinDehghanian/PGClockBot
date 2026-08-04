"""Phase C2 — write authorization: no owner mutation fallback."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.pasarguard import PasarGuardError


class StaffPgWriteClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_owner_client(self):
        from app.api.pg_pages import _staff_pg

        fake = MagicMock()
        with patch("app.api.pg_pages.get_pg", return_value=fake):
            client, as_owner = await _staff_pg(AsyncMock(), {"role": "admin"})
        self.assertTrue(as_owner)
        self.assertIs(client, fake)

    async def test_reseller_own_client(self):
        from app.api.pg_pages import _staff_pg

        fake = MagicMock()
        with patch(
            "app.api.pg_pages.get_pg_for_reseller",
            new=AsyncMock(return_value=fake),
        ):
            client, as_owner = await _staff_pg(
                AsyncMock(),
                {"role": "reseller", "bot_user_id": 7, "pg_admin_username": "r"},
            )
        self.assertFalse(as_owner)
        self.assertIs(client, fake)

    async def test_pg_staff_fail_closed(self):
        from app.api.pg_pages import _staff_pg

        with patch("app.api.pg_pages.get_pg") as gp:
            with self.assertRaises(PasarGuardError) as ctx:
                await _staff_pg(
                    AsyncMock(),
                    {"role": "pg_staff", "pg_admin_username": "s1"},
                )
        gp.assert_not_called()
        self.assertIn("اعتبارنامه", str(ctx.exception))


class AssertOwnedUserWritePreludeTests(unittest.IsolatedAsyncioTestCase):
    async def test_pg_staff_returns_none_without_owner_probe(self):
        from app.api.pg_pages import _assert_owned_user

        owner = AsyncMock()
        owner.get_user_by_id = AsyncMock(return_value={"id": 1, "admin": "s1"})
        with patch("app.api.pg_pages.get_pg", return_value=owner):
            out = await _assert_owned_user(
                {"role": "pg_staff", "pg_admin_username": "s1"},
                1,
                session=AsyncMock(),
            )
        self.assertIsNone(out)
        owner.get_user_by_id.assert_not_awaited()


class ExactActionSourceGuards(unittest.TestCase):
    def test_mutations_gate_exact_actions(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        for needle in (
            'staff_pg_action(staff, "templates", "create")',
            'staff_pg_action(staff, "templates", "delete")',
            'staff_pg_action(staff, "groups", "create")',
            'staff_pg_action(staff, "hosts", "create")',
            'staff_pg_action(staff, "nodes", "reconnect")',
        ):
            self.assertIn(needle, src)

    def test_staff_pg_no_pg_staff_owner_return(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        fn = src[src.find("async def _staff_pg") : src.find("async def _assert_owned_user")]
        self.assertIn("بدون اعتبارنامه اختصاصی", fn)
        # Only platform-admin branch may return owner client
        self.assertEqual(fn.count("return get_pg(), True"), 1)
        self.assertIn("raise PasarGuardError", fn)
        self.assertNotIn('staff.get("role") == "pg_staff"', fn)


if __name__ == "__main__":
    unittest.main()
