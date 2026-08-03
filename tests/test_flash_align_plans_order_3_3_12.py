"""3.3.12 — flash text/icon alignment, tip color, wholesale button order."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
PLANS = (ROOT / "app/web/templates/plans.html").read_text(encoding="utf-8")


class FlashAlignColorTests(unittest.TestCase):
    def test_flash_vertically_centers_icon_and_text(self):
        block = CSS.split(".flash {")[1].split("}")[0]
        self.assertIn("align-items: center", block)
        self.assertNotIn("align-items: flex-start", block)

    def test_flash_keeps_severity_text_colors(self):
        # Tip-box color change must not strip flash ok/err/warn body colors.
        self.assertIn("color: #86efac", CSS.split(".flash.ok {")[1].split("}")[0])
        self.assertIn("color: #fca5a5", CSS.split(".flash.err {")[1].split("}")[0])
        self.assertIn("color: #fde047", CSS.split(".flash.warn {")[1].split("}")[0])


class PlansWholesaleButtonOrderTests(unittest.TestCase):
    def test_wholesale_is_last_action_button(self):
        m = re.search(
            r'page-title-actions actions">(.*?)</div>',
            PLANS,
            re.S,
        )
        self.assertIsNotNone(m)
        buttons = re.findall(r'data-modal-open="([^"]+)"', m.group(1))
        self.assertEqual(
            buttons,
            ["modal-trial", "modal-custom", "modal-plan-create", "modal-wholesale"],
        )
        self.assertEqual(buttons[-1], "modal-wholesale")


class GaugeCenterLabelTests(unittest.TestCase):
    def test_center_label_is_mande(self):
        macro = (ROOT / "app/web/templates/_pg_quota_gauges.html").read_text(encoding="utf-8")
        self.assertIn("<span>مانده</span>", macro)
        self.assertNotIn("<span>باقی</span>", macro)


class VersionBumpTests(unittest.TestCase):
    def test_version_at_least_3_3_12(self):
        from app.version import __version__

        self.assertGreaterEqual(tuple(int(x) for x in __version__.split(".")), (3, 3, 12))
        notes = (ROOT / "app/services/release_notes.py").read_text(encoding="utf-8")
        self.assertIn('"3.3.12"', notes)
        self.assertIn("مانده", notes)


if __name__ == "__main__":
    unittest.main()
