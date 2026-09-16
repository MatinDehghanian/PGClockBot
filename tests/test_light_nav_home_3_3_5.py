"""Light theme: accordion section borders/fills restored; title capsule press/hover only."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
NAV_MODES = ROOT / "app/web/static/panel-nav-modes.css"


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

    def test_light_section_borders_and_collapsed_fills(self):
        css = CSS.read_text(encoding="utf-8")
        home = css.split('html[data-theme="light"] .nav-section-home {', 1)[1].split("}", 1)[0]
        self.assertIn("border-color: var(--border);", home)
        home_collapsed = css.split(
            'html[data-theme="light"] .nav-section-home.is-collapsed {', 1
        )[1].split("}", 1)[0]
        self.assertIn("var(--foreground)", home_collapsed)
        bot = css.split('html[data-theme="light"] .nav-section-bot {', 1)[1].split("}", 1)[0]
        self.assertIn("var(--bot-line)", bot)
        pg = css.split('html[data-theme="light"] .nav-section-pg {', 1)[1].split("}", 1)[0]
        self.assertIn("var(--pg-line)", pg)
        self.assertNotIn("rgba(0, 0, 0, 0.28)", home + bot + pg)

    def test_dark_section_borders_present(self):
        css = CSS.read_text(encoding="utf-8")
        # Skip the shared group selector; assert per-section chrome blocks.
        home = css.split(".nav-section-home {\n  margin-top: var(--space-1);\n", 1)[1].split("}", 1)[0]
        self.assertIn("border: 1px solid var(--border);", home)
        bot = css.split(".nav-section-bot {\n  border:", 1)[1].split("}", 1)[0]
        self.assertIn("var(--bot-line)", bot)
        pg = css.split(".nav-section-pg {\n  border:", 1)[1].split("}", 1)[0]
        self.assertIn("var(--pg-line)", pg)

    def test_title_capsule_not_sticky_when_open(self):
        css = CSS.read_text(encoding="utf-8")
        modes = NAV_MODES.read_text(encoding="utf-8")
        self.assertIn("border-radius: 999px", modes)
        # Must not keep title chrome sticky while section is open
        self.assertNotIn(":not(.is-collapsed) > .nav-label-toggle", css)
        self.assertIn(".nav-section-bot > .nav-label-toggle:active", css)
        self.assertIn(".nav-section-pg > .nav-label-toggle:active", css)

    def test_home_active_and_hover_are_neutral(self):
        css = CSS.read_text(encoding="utf-8")
        marker = 'html[data-theme="light"] .nav-item-home.active'
        self.assertIn(marker, css)
        start = css.index(marker)
        end = css.index('html[data-theme="light"] .nav-section-bot', start)
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
