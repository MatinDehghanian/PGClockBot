"""RTL/Persian UI guards + plans→PG template ACL bypass fix."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")


class RtlPlaceholderTests(unittest.TestCase):
    def test_placeholder_inherits_field_direction(self):
        self.assertIn("text-align: start;", CSS)
        self.assertIn("direction: inherit;", CSS)
        self.assertIn('input[dir="ltr"]::placeholder', CSS)
        self.assertIn('input[dir="ltr"],\ntextarea[dir="ltr"]', CSS)
        self.assertNotIn(
            "input::placeholder,\ntextarea::placeholder {\n  color: #52525b;\n  font-size: inherit;\n  font-weight: 400;\n  opacity: 1;\n  text-align: right;\n  direction: rtl;\n}",
            CSS,
        )


class RtlLtrHotspotsTests(unittest.TestCase):
    def test_login_fields_ltr(self):
        src = (ROOT / "app/web/templates/login.html").read_text(encoding="utf-8")
        self.assertIn('name="username"', src)
        self.assertIn('dir="ltr"', src)
        self.assertIn('name="password"', src)

    def test_hosts_users_nodes_ltr(self):
        hosts = (ROOT / "app/web/templates/pg_hosts.html").read_text(encoding="utf-8")
        users = (ROOT / "app/web/templates/pg_users.html").read_text(encoding="utf-8")
        nodes = (ROOT / "app/web/templates/pg_nodes.html").read_text(encoding="utf-8")
        self.assertIn('dir="ltr"', hosts)
        self.assertIn('class="mono" dir="ltr"', users)
        self.assertIn('class="mono" dir="ltr"', nodes)

    def test_commission_uses_persian_percent(self):
        src = (ROOT / "app/web/templates/resellers.html").read_text(encoding="utf-8")
        self.assertIn("commission_percent }}٪", src)
        self.assertNotIn("commission_percent }}%", src)

    def test_payg_rate_isolates_amount(self):
        src = (ROOT / "app/web/templates/_reseller_edit_body.html").read_text(encoding="utf-8")
        self.assertIn('dir="ltr" class="num-ratio"', src)
        self.assertIn("/ گیگ", src)


class PlansTemplateCreateAclTests(unittest.TestCase):
    def test_helper_requires_exact_create_action(self):
        from app.services.plans_catalog import staff_can_create_pg_template

        reseller = {
            "role": "reseller",
            "pg_writes": {"templates": True},
            "pg_actions": {"templates": {"create": False, "update": True, "delete": False}},
        }
        self.assertFalse(staff_can_create_pg_template(reseller))
        reseller["pg_actions"]["templates"]["create"] = True
        self.assertTrue(staff_can_create_pg_template(reseller))

    def test_plans_create_uses_staff_pg_not_owner_token(self):
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        block = src.split("if also_create_template:", 1)[1].split("from app.services.orders import parse_naming_form", 1)[0]
        self.assertIn("_staff_pg", block)
        self.assertIn("create_user_template", block)
        self.assertNotIn("get_pg().create_user_template", block)
        self.assertIn("staff_can_create_pg_template", block)


class PgMutationServerAclTests(unittest.TestCase):
    """Sensitive /pg write routes must gate on staff_pg_action / user actions."""

    def test_hosts_templates_edit_check_update(self):
        src = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn('staff_pg_action(staff, "hosts", "update")', src)
        self.assertIn('staff_pg_action(staff, "templates", "update")', src)
        self.assertIn('@app.post("/pg/hosts/{host_id}/edit")', src)
        self.assertIn('@app.post("/pg/templates/{template_id}/edit")', src)

    def test_no_owner_token_in_staff_template_create_on_plans(self):
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        # Global get_pg().create_user_template must not appear after also_create_template fix
        self.assertNotIn("await get_pg().create_user_template(", src)


if __name__ == "__main__":
    unittest.main()
