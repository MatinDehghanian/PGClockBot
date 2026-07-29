"""PG user create (template + custom) wiring tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock


class PgUserCreateUiTests(unittest.TestCase):
    def test_template_has_custom_mode(self):
        src = Path("app/web/templates/pg_users.html").read_text(encoding="utf-8")
        self.assertIn('name="mode"', src)
        self.assertIn("data_limit_gb", src)
        self.assertIn("duration_days", src)
        self.assertIn("pg-user-mode-custom", src)
        self.assertIn("گروه + حجم + مدت", src)
        self.assertIn("data-copy", src)
        self.assertIn("modal-pg-user-edit", src)
        self.assertIn("ویرایش", src)

    def test_post_handler_supports_custom(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn("create_user_from_template", src)
        self.assertIn("create_user(", src)
        self.assertIn("groups_allowed_for_staff", src)
        self.assertIn("require_template", src)
        self.assertIn("parse_group_ids_from_form", src)
        self.assertIn("modify_user_by_id", src)
        self.assertIn("/pg/users/{user_id}/edit", src)
        self.assertIn("days * 86400", src)

    def test_nodes_reconnect_for_viewers(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn("can_reconnect", src)
        self.assertIn("reconnect_node", src)
        tpl = Path("app/web/templates/pg_nodes.html").read_text(encoding="utf-8")
        self.assertIn("اتصال مجدد", tpl)
        self.assertIn("can_reconnect", tpl)


class PgUserCreateLogicTests(unittest.TestCase):
    def test_groups_allowed_helpers(self):
        from app.services.plans_catalog import groups_allowed_for_staff, template_allowed_for_staff

        admin = {"role": "admin"}
        self.assertTrue(groups_allowed_for_staff(admin, [1, 2]))
        self.assertTrue(template_allowed_for_staff(admin, 9))

        reseller = {
            "role": "reseller",
            "pg_access": {"allowed_group_ids": [3, 5], "allowed_template_ids": [10]},
        }
        self.assertTrue(groups_allowed_for_staff(reseller, [3]))
        self.assertFalse(groups_allowed_for_staff(reseller, [3, 9]))
        self.assertTrue(template_allowed_for_staff(reseller, 10))
        self.assertFalse(template_allowed_for_staff(reseller, 11))


if __name__ == "__main__":
    unittest.main()
