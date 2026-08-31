"""Light theme: closed mobile drawer must not leave a white slab."""

from __future__ import annotations

import unittest
from pathlib import Path

from css_blocks import at_rule, rule


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"


class LightThemeClosedDrawerTests(unittest.TestCase):
    def test_mobile_light_side_shell_stays_transparent(self):
        css = CSS.read_text(encoding="utf-8-sig")
        # Global light rule may paint desktop .side white…
        self.assertIn('html[data-theme="light"] .side', css)
        # …but mobile must force the fixed shell back to transparent.
        mobile = at_rule(css, "@media (max-width: 900px)")
        self.assertIn('html[data-theme="light"] .side', mobile)
        light_side = rule(mobile, 'html[data-theme="light"] .side')
        self.assertIn("background: transparent;", light_side)
        self.assertIn("background-color: transparent;", light_side)
        # Closed drawer still slides via .side-panel (which keeps bg-card paint).
        panel = rule(mobile, ".side-panel")
        self.assertIn("background: var(--bg-card);", panel)
        self.assertIn("transform: translate3d(calc(100% + 24px), 0, 0);", panel)


if __name__ == "__main__":
    unittest.main()
