"""v4.10.6 — create reseller from web panel selects a plan (fixed/PAYG)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/web/templates/resellers.html").read_text(encoding="utf-8")
API = (ROOT / "app/api/reseller_pages.py").read_text(encoding="utf-8")


class ResellerCreatePlanUiTests(unittest.TestCase):
    def test_create_modal_has_plan_select_not_commission(self):
        start = HTML.find('id="modal-reseller-create"')
        end = HTML.find('id="modal-reseller-edit"')
        modal = HTML[start:end]
        self.assertIn('name="plan_id"', modal)
        self.assertIn("پلن نمایندگی", modal)
        self.assertIn("— انتخاب پلن —", modal)
        self.assertIn("[PAYG]", modal)
        self.assertIn("[ثابت]", modal)
        self.assertIn("reseller_plans", modal)
        self.assertNotIn('name="commission_percent"', modal)
        self.assertNotIn("کمیسیون ٪", modal)

    def test_plan_select_matches_pg_admins_pattern(self):
        start = HTML.find('id="modal-reseller-create"')
        end = HTML.find('id="modal-reseller-edit"')
        modal = HTML[start:end]
        self.assertIn("required", modal)
        self.assertIn("disabled", modal)
        self.assertIn("هنوز پلن نمایندگی فعالی ندارید", modal)


class ResellerCreatePlanApiTests(unittest.TestCase):
    def test_list_passes_active_plans(self):
        self.assertIn("list_active_reseller_plans", API)
        self.assertIn('"reseller_plans": reseller_plans', API)

    def test_create_requires_active_plan(self):
        fn = API[
            API.find("async def reseller_create") : API.find(
                "async def reseller_edit_page"
            )
        ]
        self.assertIn('form.get("plan_id")', fn)
        self.assertIn("انتخاب پلن نمایندگی الزامی است", fn)
        self.assertIn("پلن نمایندگی نامعتبر یا غیرفعال است", fn)
        self.assertIn("plan=plan", fn)
        self.assertNotIn("commission_percent", fn)
        self.assertNotIn('form.get("commission_percent")', fn)


class VersionTests(unittest.TestCase):
    def test_version(self):
        from app.version import __version__

        self.assertEqual(__version__, "4.10.6")
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "4.10.6")


if __name__ == "__main__":
    unittest.main()
