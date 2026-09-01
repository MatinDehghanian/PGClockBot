"""Bulk op count badges must match their button variant tint."""

from __future__ import annotations

import unittest
from pathlib import Path

from css_blocks import rule

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
MACROS = (ROOT / "app/web/templates/macros.html").read_text(encoding="utf-8")


class BulkBadgeTonalTests(unittest.TestCase):
    def test_no_blanket_gray_light_override(self):
        self.assertNotIn('html[data-theme="light"] .table-bulk-op-count {', CSS)
        self.assertNotIn("rgba(0, 0, 0, 0.18)", CSS.split(".table-bulk-op-count")[1][:800])

    def test_each_variant_has_tonal_badge(self):
        for variant in ("btn-ghost", "btn-ok", "btn-warn", "btn-danger"):
            sel = f".table-bulk-op.{variant} .table-bulk-op-count"
            body = rule(CSS, sel)
            self.assertIn("border-color:", body, msg=variant)
            self.assertIn("background:", body, msg=variant)
            self.assertIn("color:", body, msg=variant)

    def test_light_theme_per_variant_badges(self):
        for variant in ("btn-ghost", "btn-ok", "btn-warn", "btn-danger"):
            sel = f'html[data-theme="light"] .table-bulk-op.{variant} .table-bulk-op-count'
            body = rule(CSS, sel)
            self.assertIn("background:", body, msg=variant)

    def test_warn_actions_default_to_btn_warn_in_macro(self):
        self.assertIn("'btn-warn' if action.warn else 'btn-ghost'", MACROS)


if __name__ == "__main__":
    unittest.main()
