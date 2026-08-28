"""Tests for inbox dismissals, payment destinations, dashboard order."""

from __future__ import annotations

import json
from pathlib import Path

import unittest


class InboxDismissalsTests(unittest.TestCase):
    def test_dismiss_service_file(self):
        src = Path("app/services/inbox_dismissals.py").read_text(encoding="utf-8")
        self.assertIn("MODE_24H", src)
        self.assertIn("MODE_FOREVER", src)
        self.assertIn("filter_inbox_context", src)
        self.assertIn("filter_action_center_for_staff", src)
        self.assertIn("clear_staff_dismissals", src)
        self.assertIn("staff_dismiss_key_candidates", src)
        self.assertIn("_action_center_active_keys", src)
        self.assertIn("SNOOZE_HOURS = 24", src)

    def test_dismiss_model(self):
        src = Path("app/db/models.py").read_text(encoding="utf-8")
        self.assertIn("class PanelInboxDismissal", src)


class PaymentDestinationsTests(unittest.TestCase):
    def test_legacy_migration_logic(self):
        src = Path("app/services/payment_destinations.py").read_text(encoding="utf-8")
        self.assertIn("def migrate_legacy_payment_settings", src)
        self.assertIn("def enrich_payment_settings", src)
        self.assertIn("KEY_CARDS", src)

    def test_settings_form_fields(self):
        src = Path("app/services/users.py").read_text(encoding="utf-8")
        self.assertIn('"payment_cards"', src)
        self.assertIn('"payment_gateways"', src)
        self.assertIn('"payment_crypto_wallets"', src)
        field = Path("app/web/templates/_settings_field.html").read_text(encoding="utf-8")
        self.assertIn("data-pay-dest", field)


class DashboardAndBulkTests(unittest.TestCase):
    def test_home_ops_queue_before_sales(self):
        ops = Path("app/web/templates/_home_ops.html").read_text(encoding="utf-8")
        q = ops.find("home-action-card")
        s = ops.find("home-periods-card")
        self.assertGreater(q, 0)
        self.assertGreater(s, 0)
        self.assertLess(q, s)

    def test_bulk_select_markup(self):
        macros = Path("app/web/templates/macros.html").read_text(encoding="utf-8")
        panel_js = Path("app/web/static/panel.js").read_text(encoding="utf-8")
        panel_css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn("table_bulk_bar", macros)
        self.assertIn("table-bulk-check", macros)
        self.assertIn("table-bulk-op-count", macros)
        self.assertIn("data-bulk-select", Path("app/web/templates/users.html").read_text(encoding="utf-8"))
        self.assertIn("data-table-bulk-bar", panel_js)
        self.assertIn("openModal('modal-inbox-dismiss')", panel_js)
        self.assertIn("is-bulk-selected", panel_js)
        self.assertIn("panelConfirm", panel_js.split("Table bulk row selection")[1])
        self.assertIn("eligibleIds", panel_js)
        self.assertIn("rgba(249, 115, 22, 0.08)", panel_css)
        self.assertIn("width: 20px !important", panel_css)
        self.assertIn("height: 20px !important", panel_css)
        self.assertIn("border-radius: 50%", panel_css)
        self.assertIn("margin: 0 !important", panel_css.split("Table bulk selection")[1].split("tbody tr.is-bulk-selected")[0])
        self.assertIn("align-items: center", panel_css.split("Table bulk selection")[1].split("tbody tr.is-bulk-selected")[0])
        self.assertNotIn("border-radius: 4px", panel_css.split("Table bulk selection")[1].split("tbody tr.is-bulk-selected")[0])
        self.assertIn(".table-bulk-op-count", panel_css)

    def test_pay_dest_delete_button(self):
        js = Path("app/web/static/panel.js").read_text(encoding="utf-8")
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn("pay-dest-remove-btn", js)
        self.assertIn("btn-danger btn-sm pay-dest-remove", js)
        self.assertNotIn("pay-dest-actions", js)
        self.assertIn(".pay-dest-remove-btn", css)

    def test_inbox_dismiss_modal(self):
        base = Path("app/web/templates/base.html").read_text(encoding="utf-8")
        self.assertIn("modal-inbox-dismiss", base)
        self.assertIn("/inbox/dismiss", base)


if __name__ == "__main__":
    unittest.main()
