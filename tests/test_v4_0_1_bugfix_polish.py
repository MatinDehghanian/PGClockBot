"""v4.0.1 regression contracts — bugfix & production polish (no architecture change)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]


class StaffHomeSessionCrashFix(unittest.TestCase):
    def test_pg_home_does_not_touch_request_session(self):
        src = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        home = src[src.find("async def pg_home") : src.find("async def pg_users")]
        self.assertNotIn("request.session.get", home)
        # staff.get("username") now lives in _pg_chrome_context(), a shared
        # helper pg_home() calls for its ticket-alert/remediation chrome —
        # still staff-dict-only (no request.session), just extracted so
        # pg_home_body() can reuse the same fast-chrome logic.
        self.assertIn("await _pg_chrome_context(request, staff, session)", home)
        chrome_helper = src[
            src.find("async def _pg_chrome_context") : src.find("async def pg_home")
        ]
        self.assertNotIn("request.session.get", chrome_helper)
        self.assertIn('staff.get("username")', chrome_helper)


class StaffEditPreservesActive(unittest.TestCase):
    def test_staff_route_does_not_force_active(self):
        src = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        fn = src[
            src.find("async def pg_admins_web_access_staff") : src.find(
                "async def pg_admins_web_access_reseller"
            )
        ]
        self.assertIn("is_active=None", fn)
        # New grant may set is_active=True; edit path must not force reactivation
        edit_block = fn[fn.find("if existing:") : fn.find("else:")]
        self.assertIn("is_active=None", edit_block)
        self.assertNotIn("is_active=True", edit_block)


class CredentialGateOnRequirePgPerm(unittest.TestCase):
    def test_require_pg_perm_uses_effective_menu(self):
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        dep = src[src.find("def require_pg_perm") : src.find("@app.middleware")]
        self.assertIn("effective_pg_menu_keys", dep)
        self.assertIn('raise NotAdmin(redirect="/pg")', dep)


class BackupStatusEndpoint(unittest.TestCase):
    def test_status_route_registered(self):
        src = (ROOT / "app/api/backup_pages.py").read_text(encoding="utf-8")
        self.assertIn('"/backup/status"', src)
        self.assertIn("resolve_stale_restore_status", src)

    def test_skip_unread_includes_backup_status(self):
        src = (ROOT / "app/services/panel_tickets.py").read_text(encoding="utf-8")
        self.assertIn('"/backup/status"', src)

    def test_backup_template_has_progress_ui(self):
        tpl = (ROOT / "app/web/templates/_settings_backup.html").read_text(encoding="utf-8")
        self.assertIn("/backup/status", tpl)
        self.assertIn("backup-restore-fill", tpl)
        self.assertIn("backup-restore-steps", tpl)
        self.assertIn("progress-wrap", tpl)
        self.assertIn("در حال ریستور", tpl)

    def test_backup_restore_async_service(self):
        src = (ROOT / "app/services/backup.py").read_text(encoding="utf-8")
        self.assertIn("start_restore_async", src)
        self.assertIn("RESTORE_STEPS", src)
        self.assertIn("awaiting_restart", src)
        self.assertIn("percent", src)

    def test_backup_restore_returns_json(self):
        src = (ROOT / "app/api/backup_pages.py").read_text(encoding="utf-8")
        self.assertIn("start_restore_async", src)
        self.assertIn("JSONResponse", src)
        self.assertIn("_wants_json", src)
        self.assertNotIn("/login?restarting", src)


class UxCopyConsistency(unittest.TestCase):
    def test_no_owner_english_in_staff_home(self):
        tpl = (ROOT / "app/web/templates/pg_home.html").read_text(encoding="utf-8")
        self.assertNotIn("Owner", tpl)
        self.assertIn("ادمین اصلی", tpl)

    def test_no_phase_d3_jargon_in_admins(self):
        tpl = (ROOT / "app/web/templates/pg_admins.html").read_text(encoding="utf-8")
        self.assertNotIn("فاز D3", tpl)
        self.assertIn("یتیم", tpl)

    def test_reseller_setup_page_removed(self):
        self.assertFalse((ROOT / "app/web/templates/reseller_setup.html").exists())
        self.assertFalse((ROOT / "app/api/reseller_setup.py").exists())

    def test_no_mutate_jargon_in_staff_pg_error(self):
        src = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        fn = src[src.find("async def _staff_pg") : src.find("async def _assert_owned_user")]
        self.assertNotIn("mutate", fn)
        self.assertIn("راه حل", fn)

    def test_no_provision_english_in_reseller_pg_error(self):
        src = (ROOT / "app/services/pasarguard.py").read_text(encoding="utf-8")
        self.assertNotIn("provision کنید", src)
        self.assertIn("راه حل", src)


class EncryptBeforePgSync(unittest.IsolatedAsyncioTestCase):
    async def test_encrypt_failure_skips_modify_admin(self):
        from app.services import pg_staff_access as psa

        session = AsyncMock()
        session.add = MagicMock()
        pg = MagicMock()
        pg.modify_admin = AsyncMock()
        with (
            patch.object(psa, "conflict_message_for_new_grant", new=AsyncMock(return_value=None)),
            patch.object(psa, "_username_taken", new=AsyncMock(return_value=None)),
            patch.object(psa, "resolve_pg_role_id_for_admin", new=AsyncMock(return_value=1)),
            patch.object(psa, "hash_password", return_value="h"),
            patch("app.services.pasarguard.get_pg", return_value=pg),
            patch("app.services.pasarguard.reset_pg"),
            patch("app.services.secret_box.encrypt_secret", return_value=None),
        ):
            row, err = await psa.grant_web_access(
                session,
                pg_username="staffy",
                web_username="staffy",
                password="AaBb12!secretXX",
            )
        self.assertIsNone(row)
        self.assertIn("رمز‌گذاری", err or "")
        pg.modify_admin.assert_not_awaited()


class MisalignedSelfServeBlocked(unittest.IsolatedAsyncioTestCase):
    async def test_change_staff_blocks_when_misaligned(self):
        from app.services import pg_staff_access as psa

        row = MagicMock()
        row.id = 1
        row.web_username = "oldname"
        row.pg_username = "pgname"
        row.web_password_hash = "hash"
        with (
            patch.object(psa, "verify_password_hash", return_value=True),
            patch.object(psa, "validate_password_strength", return_value=(True, "")),
            patch.object(psa, "validate_web_username", return_value=("pgname", None)),
        ):
            updated, err = await psa.change_staff_credentials(
                AsyncMock(),
                row,
                old_username="oldname",
                current_password="x",
                new_username="pgname",
                new_password="AaBb12!secretXX",
            )
        self.assertIsNone(updated)
        self.assertIn("ادمین اصلی", err or "")
        self.assertIn("هم‌ترازسازی", err or "")


class GetPgForStaffCaseFold(unittest.TestCase):
    def test_lookup_uses_lower(self):
        src = (ROOT / "app/services/pasarguard.py").read_text(encoding="utf-8")
        fn = src[src.find("async def get_pg_for_staff") : src.find("def public_pg_api_base")]
        self.assertIn("func.lower", fn)
        self.assertIn("strip().lower()", fn)


class NodeBusyUi(unittest.TestCase):
    def test_reconnect_busy_form(self):
        tpl = (ROOT / "app/web/templates/pg_nodes.html").read_text(encoding="utf-8")
        self.assertIn("js-busy-form", tpl)
        self.assertIn("در حال اتصال", tpl)


if __name__ == "__main__":
    unittest.main()
