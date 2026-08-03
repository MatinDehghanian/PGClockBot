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

    def test_flash_tip_text_matches_title_foreground(self):
        for kind in ("ok", "err", "warn"):
            block = CSS.split(f".flash.{kind} {{")[1].split("}")[0]
            self.assertIn("color: var(--foreground)", block)
            self.assertNotIn("#86efac", block)
            self.assertNotIn("#fca5a5", block)
            self.assertNotIn("#fde047", block)
        light_ok = CSS.split('html[data-theme="light"] .flash.ok {')[1].split("}")[0]
        self.assertIn("color: var(--foreground)", light_ok)
        self.assertNotIn("#15803d", light_ok)


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


class VersionBumpTests(unittest.TestCase):
    def test_version_is_3_3_12(self):
        from app.version import __version__

        self.assertEqual(__version__, "3.3.12")
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "3.3.12")
        notes = (ROOT / "app/services/release_notes.py").read_text(encoding="utf-8")
        self.assertIn('"3.3.12"', notes)


if __name__ == "__main__":
    unittest.main()
