"""Confirm modal reason field: only for delete user/reseller/admin."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
BASE = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
TEMPLATES = ROOT / "app/web/templates"


class ConfirmReasonRenderOnlyWhenRequired(unittest.TestCase):
    def test_base_has_slot_not_static_reason_field(self):
        self.assertIn('id="confirm-reason-slot"', BASE)
        self.assertIn("confirm-reason-slot", JS)
        # Must NOT keep a permanent reason textarea in the modal shell
        confirm = BASE.split('id="modal-confirm"', 1)[1].split("</div>\n  <script", 1)[0]
        self.assertNotIn('id="confirm-reason"', confirm)
        self.assertNotIn("confirm-reason-wrap", confirm)
        self.assertIn("injected by panel.js only when requireReason=true", confirm)

    def test_js_renders_reason_only_when_require_reason_true(self):
        self.assertIn("requireReason === true", JS)
        self.assertIn("function renderReasonField", JS)
        self.assertIn("function clearReasonField", JS)
        self.assertIn("reasonSlot.innerHTML = ''", JS)
        # Presence of data-confirm-reason alone must go through attrTruthy → requireReason
        self.assertIn("attrTruthy(src, 'data-confirm-reason')", JS)
        self.assertIn("requireReason: requireReason", JS)
        # Non-delete panelConfirm (rollback) must not default reason on
        self.assertNotIn("needReason = !!opts.reason", JS)

    def test_form_field_hidden_cannot_override_display(self):
        self.assertIn(".form-field[hidden]", CSS)
        self.assertIn("#confirm-reason-slot[hidden]", CSS)
        block = CSS.split(".form-field[hidden]", 1)[1].split("}", 1)[0]
        self.assertIn("display: none !important", block)

    def test_open_modal_does_not_autofocus(self):
        block = JS.split("function openModal")[1].split("window.openModal")[0]
        self.assertIn("Never autofocus", block)
        self.assertNotIn(".focus()", block)


class ConfirmReasonOnlyOnAccountDeletes(unittest.TestCase):
    ALLOWED = {
        "users.html",
        "resellers.html",
        "_reseller_edit_body.html",
        "_user_edit_body.html",
        "pg_admins.html",
    }

    def test_only_allowed_templates_set_data_confirm_reason(self):
        offenders = []
        for path in TEMPLATES.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            if "data-confirm-reason" not in text:
                continue
            if path.name not in self.ALLOWED:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], msg=f"unexpected reason attrs: {offenders}")

    def test_non_delete_confirms_have_no_reason(self):
        samples = {
            "finance.html": ["/approve", "/reject", "/cancel"],
            "pg_users.html": ["/disable", "/enable", "/reset", "/revoke"],
            "pg_nodes.html": ["/reset", "/delete"],
            "_settings_ssl.html": ["غیرفعال‌سازی HTTPS"],
        }
        for name, needles in samples.items():
            src = (TEMPLATES / name).read_text(encoding="utf-8")
            self.assertNotIn("data-confirm-reason", src, msg=name)
            for n in needles:
                self.assertIn(n, src, msg=f"{name} missing {n}")
        # User edit: wallet/extend confirms must stay reason-free; delete may require reason
        user_edit = (TEMPLATES / "_user_edit_body.html").read_text(encoding="utf-8")
        for needle in ("/extend", "شارژ", "/wallet-credit", "/renew"):
            self.assertIn(needle, user_edit)
        credit = user_edit.split("/wallet-credit", 1)[1].split("</form>", 1)[0]
        extend = user_edit.split("/extend", 1)[1].split("</form>", 1)[0]
        self.assertNotIn("data-confirm-reason", credit)
        self.assertNotIn("data-confirm-reason", extend)
        delete = user_edit.split("/users/{{ user.id }}/delete", 1)[1].split("</form>", 1)[0]
        self.assertIn('data-confirm-reason="1"', delete)

    def test_user_reseller_admin_deletes_require_reason(self):
        users = (TEMPLATES / "users.html").read_text(encoding="utf-8")
        delete = users.split("/users/{{ u.id }}/delete", 1)[1].split("</form>", 1)[0]
        self.assertIn('data-confirm-reason="1"', delete)
        block = users.split("/users/{{ u.id }}/block", 1)[1].split("</form>", 1)[0]
        self.assertNotIn("data-confirm-reason", block)

        resellers = (TEMPLATES / "resellers.html").read_text(encoding="utf-8")
        self.assertIn('data-confirm-reason="1"', resellers)
        self.assertIn("/resellers/{{ u.id }}/delete", resellers)

        admins = (TEMPLATES / "pg_admins.html").read_text(encoding="utf-8")
        adm_del = admins.split("/pg/admins/{{ uname }}/delete", 1)[1].split("</form>", 1)[0]
        self.assertIn('data-confirm-reason="1"', adm_del)
        self.assertIn('name="reason"', adm_del)


class ConfirmReasonBackendEnforced(unittest.TestCase):
    def test_users_delete_requires_reason(self):
        api = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        block = api.split("async def users_delete", 1)[1].split("\n    @app.", 1)[0]
        self.assertIn("extract_delete_reason", block)
        self.assertIn("delete_reason_too_short", block)
        self.assertIn("علت حذف کاربر الزامی است", block)
        self.assertIn("notify_account_edit", block)
        self.assertIn('event="user_delete"', block)

    def test_reseller_delete_requires_reason(self):
        api = (ROOT / "app/api/reseller_pages.py").read_text(encoding="utf-8")
        self.assertIn("علت حذف نمایندگی الزامی است", api)
        self.assertIn("علت حذف کاربر الزامی است", api)
        self.assertIn("notify_reseller_revoked", api)
        self.assertIn("extract_delete_reason", api)

    def test_pg_admin_delete_requires_reason(self):
        api = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        block = api.split("async def pg_admins_delete", 1)[1].split("\n    @app.", 1)[0]
        self.assertIn("extract_delete_reason", block)
        self.assertIn("delete_reason_too_short", block)
        self.assertIn("علت حذف ادمین الزامی است", block)
        self.assertIn("reason=reason", block)
        self.assertNotIn('reason="حذف ادمین پاسارگارد از وب‌پنل"', block)


class NoOrphanReasonCssJs(unittest.TestCase):
    def test_no_permanent_confirm_reason_css_show_hacks(self):
        # Must not force-show reason wrap
        self.assertNotIn("#confirm-reason-wrap {", CSS)
        self.assertNotIn("#confirm-reason-wrap{", CSS)

    def test_project_templates_reason_attr_count(self):
        """Every data-confirm-reason flag must sit on a delete form for accounts."""
        hits = []
        for path in TEMPLATES.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(r"\bdata-confirm-reason(?:\s*=\s*[\"'][^\"']*[\"'])?", text):
                # Skip -label / -name / -min variants
                after = text[m.start() : m.start() + 28]
                if after.startswith("data-confirm-reason-"):
                    continue
                start = max(0, m.start() - 700)
                end = min(len(text), m.start() + 200)
                ctx = text[start:end]
                hits.append((path.name, ctx))
        self.assertGreaterEqual(len(hits), 5)
        for name, ctx in hits:
            self.assertTrue(
                "/delete" in ctx or "delete-user" in ctx,
                msg=f"{name} reason not near delete: …{ctx[-160:]}",
            )


if __name__ == "__main__":
    unittest.main()
