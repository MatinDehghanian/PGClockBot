"""Light theme: accordion sections stay transparent (capsule only on title press/hover)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"


class LightNavHomeBoxTests(unittest.TestCase):
    def test_home_box_not_grouped_with_modal_backdrop(self):
        css = CSS.read_text(encoding="utf-8")
        # Regression: home was accidentally sharing rgba(0,0,0,0.28) with backdrop
        bad = re.search(
            r'html\[data-theme="light"\]\s*\.nav-section-home\s*,\s*'
            r'html\[data-theme="light"\]\s*\.ui-modal-backdrop',
            css,
        )
        self.assertIsNone(bad, "nav-section-home must not share modal backdrop background")

    def test_accordion_sections_stay_transparent(self):
        css = CSS.read_text(encoding="utf-8")
        marker = (
            'html[data-theme="light"] .nav-section-home,\n'
            'html[data-theme="light"] .nav-section-bot,\n'
            'html[data-theme="light"] .nav-section-pg'
        )
        self.assertIn(marker, css)
        block = css.split(marker, 1)[1].split("}", 1)[0]
        self.assertIn("background: transparent;", block)
        self.assertIn("border-color: transparent;", block)
        self.assertNotIn("rgba(0, 0, 0", block)

    def test_home_active_and_hover_are_neutral(self):
        css = CSS.read_text(encoding="utf-8")
        marker = 'html[data-theme="light"] .nav-item-home.active'
        self.assertIn(marker, css)
        start = css.index(marker)
        end = css.index('html[data-theme="light"] .nav-label-bot', start)
        block = css[start:end]
        self.assertIn(".nav-item-home.active", block)
        self.assertIn(".nav-item-home:hover", block)
        active = block.split(".nav-item-home.active", 1)[1].split("}", 1)[0]
        hover = block.split(".nav-item-home:hover", 1)[1].split("}", 1)[0]
        # Neutral tint from foreground — not brand orange/blue
        self.assertIn("var(--foreground)", active)
        self.assertIn("var(--foreground)", hover)
        self.assertNotIn("#ea580c", active + hover)
        self.assertNotIn("#2563eb", active + hover)
        self.assertNotIn("rgba(0, 0, 0, 0.28)", active + hover)


if __name__ == "__main__":
    unittest.main()
