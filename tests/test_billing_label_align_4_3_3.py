"""v4.3.3 — billing label rename + form-row select alignment."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BillingLabelTests(unittest.TestCase):
    def test_no_halat_billing_label(self):
        for rel in (
            "app/web/templates/_reseller_edit_body.html",
            "app/web/templates/reseller_plan_edit.html",
        ):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("حالت Billing", src)
            self.assertIn("حالت پرداخت", src)

    def test_bot_reseller_card_uses_payment_mode(self):
        src = (ROOT / "app/bot/handlers/admin.py").read_text(encoding="utf-8")
        self.assertIn("حالت پرداخت:", src)
        self.assertNotIn("حالت صورتحساب:", src)

    def test_form_row_align_start_and_select_margin(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        block = css.split(".form-row {")[1].split(".form-stack")[0]
        self.assertIn("align-items: start", block)
        self.assertIn("/* form-field already spaces title→control via gap", css)
        self.assertIn(
            ".form-row .form-field > .ui-select {\n  margin-top: 0;\n}",
            css.replace("\r\n", "\n"),
        )


class VersionTests(unittest.TestCase):
    def test_version(self):
        from app.version import __version__

        self.assertEqual(__version__, "4.3.3")
        self.assertEqual((ROOT / "VERSION").read_text().strip(), "4.3.3")


if __name__ == "__main__":
    unittest.main()
