"""Confirm modal: typed reason/phrase gates removed for deletes (pre-v10 UX)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
BASE = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
TEMPLATES = ROOT / "app/web/templates"


class ConfirmReasonSlotStillOptional(unittest.TestCase):
    def test_base_has_slot_not_static_reason_field(self):
        self.assertIn('id="confirm-reason-slot"', BASE)
        self.assertIn("confirm-reason-slot", JS)

    def test_js_still_supports_optional_reason_path(self):
        self.assertIn("requireReason", JS)
        self.assertIn("attrTruthy(src, 'data-confirm-reason')", JS)


class NoTemplateRequiresTypedReason(unittest.TestCase):
    def test_no_template_sets_data_confirm_reason(self):
        offenders = []
        for path in TEMPLATES.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"\bdata-confirm-reason(?!-|\w)", text):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], msg=f"typed-reason attrs remain: {offenders}")

    def test_account_deletes_use_simple_confirm(self):
        users = (TEMPLATES / "users.html").read_text(encoding="utf-8")
        delete = users.split("/users/{{ u.id }}/delete", 1)[1].split("</form>", 1)[0]
        self.assertIn("data-confirm=", delete)
        self.assertIn("data-confirm-danger", delete)
        self.assertNotIn("data-confirm-reason", delete)

        resellers = (TEMPLATES / "resellers.html").read_text(encoding="utf-8")
        self.assertIn("/resellers/{{ u.id }}/delete", resellers)
        self.assertNotIn("data-confirm-reason", resellers)

        admins = (TEMPLATES / "pg_admins.html").read_text(encoding="utf-8")
        self.assertNotIn("data-confirm-reason", admins)

        user_edit = (TEMPLATES / "_user_edit_body.html").read_text(encoding="utf-8")
        self.assertNotIn("data-confirm-reason", user_edit)
        self.assertNotIn("data-confirm-phrase", user_edit)


class DeleteBackendOptionalReason(unittest.TestCase):
    def test_users_delete_uses_resolve_not_gate(self):
        api = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        block = api.split("async def users_delete", 1)[1].split("\n    @app.", 1)[0]
        self.assertIn("resolve_delete_reason", block)
        self.assertNotIn("delete_reason_too_short", block)
        self.assertNotIn("علت حذف کاربر الزامی است", block)

    def test_reseller_and_admin_deletes_optional(self):
        reseller = (ROOT / "app/api/reseller_pages.py").read_text(encoding="utf-8")
        self.assertIn("resolve_delete_reason", reseller)
        self.assertNotIn("delete_reason_too_short", reseller)
        self.assertNotIn("علت حذف نمایندگی الزامی است", reseller)

        pg = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn("resolve_delete_reason", pg)
        self.assertNotIn("delete_reason_too_short", pg)


if __name__ == "__main__":
    unittest.main()
