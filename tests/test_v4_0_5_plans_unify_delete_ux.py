"""v4.0.5 — plans unify, delete wallet warn, neutral row-actions."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DeleteWalletWarnTests(unittest.TestCase):
    def test_users_delete_warns_wallet(self):
        html = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
        self.assertIn("wallet_balance", html)
        self.assertIn("موجودی کیف پول", html)
        self.assertIn("سفارش‌ها", html)

    def test_reseller_full_delete_warns_wallet(self):
        html = (ROOT / "app/web/templates/resellers.html").read_text(encoding="utf-8")
        self.assertIn("wallet_balance", html)
        self.assertIn("billing_balance", html)
        edit = (ROOT / "app/web/templates/reseller_edit.html").read_text(encoding="utf-8")
        self.assertIn("موجودی کیف پول", edit)


class PlansUnifyTests(unittest.TestCase):
    def test_single_add_button_and_unified_modal(self):
        html = (ROOT / "app/web/templates/plans.html").read_text(encoding="utf-8")
        self.assertIn("افزودن پلن", html)
        self.assertIn("modal-plan-unified", html)
        self.assertIn("plan-audience", html)
        self.assertIn("plan-kind", html)
        self.assertIn("پلن‌های کاربران", html)
        self.assertIn("reseller-plans", html)
        self.assertIn('action="/resellers/plans"', html)
        self.assertIn("commission_percent", html)
        self.assertIn("billing_mode", html)
        # Old multi-button create chrome removed
        self.assertNotIn('data-modal-open="modal-plan-create"', html)
        self.assertNotIn('data-modal-open="modal-trial"', html)

    def test_reseller_plans_redirects(self):
        src = (ROOT / "app/api/reseller_pages.py").read_text(encoding="utf-8")
        fn = src[
            src.find("async def reseller_plans_page") : src.find(
                "async def reseller_plan_create"
            )
        ]
        self.assertIn('RedirectResponse("/plans#reseller-plans"', fn)

    def test_billing_mode_on_model(self):
        src = (ROOT / "app/db/models.py").read_text(encoding="utf-8")
        block = src[src.find("class ResellerPlan") : src.find("class ResellerApplicationStatus")]
        self.assertIn("billing_mode", block)
        self.assertIn("default=0", block)  # commission default 0

    def test_session_alters_billing_mode(self):
        src = (ROOT / "app/db/session.py").read_text(encoding="utf-8")
        self.assertIn("reseller_plans ADD COLUMN billing_mode", src)

    def test_make_reseller_accepts_billing_mode(self):
        src = (ROOT / "app/services/resellers.py").read_text(encoding="utf-8")
        fn = src[src.find("async def make_reseller") : src.find("async def list_active_reseller_plans")]
        # make_reseller is before list - find differently
        fn = src[src.find("async def make_reseller") : src.find("async def make_reseller") + 3500]
        self.assertIn("billing_mode", fn)


class NeutralRowActionsTests(unittest.TestCase):
    def test_css_neutralizes_ops_except_danger_warn(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".row-actions-menu .btn:not(.btn-danger):not(.btn-warn)", css)


class VersionTests(unittest.TestCase):
    def test_version(self):
        from app.version import __version__

        self.assertEqual(__version__, "4.0.6")
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "4.0.6")


if __name__ == "__main__":
    unittest.main()
