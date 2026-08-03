"""3.4.2 — live table after flash + panel confirm modals."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
API = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
BASE = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
USERS = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
RESELLERS = (ROOT / "app/web/templates/resellers.html").read_text(encoding="utf-8")


class PanelHtmlNoStoreTests(unittest.TestCase):
    def test_html_responses_get_no_store(self):
        self.assertIn('if "text/html" in ct:', API)
        block = API.split('if "text/html" in ct:')[1].split("elif path")[0]
        self.assertIn('Cache-Control"] = "no-store, private"', block)

    def test_redirect_msg_cache_busts(self):
        block = API.split("def _redirect_msg(")[1].split("\n\n")[0]
        self.assertIn('f"_={int(time.time())}"', block)


class ConfirmModalTests(unittest.TestCase):
    def test_shared_modal_in_base(self):
        self.assertIn('id="modal-confirm"', BASE)
        self.assertIn('id="confirm-reason"', BASE)
        self.assertIn("panelConfirm", JS)
        self.assertIn("data-confirm", JS)

    def test_users_block_role_delete_use_data_confirm(self):
        self.assertIn("data-confirm=", USERS)
        self.assertIn("/users/{{ u.id }}/block", USERS)
        self.assertIn("/users/{{ u.id }}/role", USERS)
        self.assertIn("data-confirm-danger", USERS)
        self.assertNotIn("confirm(", USERS)

    def test_resellers_no_native_prompt(self):
        self.assertNotIn("prompt(", RESELLERS)
        self.assertNotIn("confirm(", RESELLERS)
        self.assertIn("data-confirm-reason", RESELLERS)
        self.assertIn('data-confirm-reason="1"', RESELLERS)

    def test_templates_drop_native_confirm_for_table_deletes(self):
        for rel in (
            "plans.html",
            "pg_users.html",
            "pg_hosts.html",
            "payments.html",
            "orders.html",
        ):
            src = (ROOT / "app/web/templates" / rel).read_text(encoding="utf-8")
            # Allow window.confirm fallback only in JS pages; table templates should not use it
            self.assertNotRegex(src, r"return confirm\(")
            self.assertIn("data-confirm=", src)


class VersionBumpTests(unittest.TestCase):
    def test_version_at_least_3_4_2(self):
        from app.version import __version__

        self.assertGreaterEqual(tuple(int(x) for x in __version__.split(".")), (3, 4, 2))
        notes = (ROOT / "app/services/release_notes.py").read_text(encoding="utf-8")
        self.assertIn('"3.4.2"', notes)


if __name__ == "__main__":
    unittest.main()
