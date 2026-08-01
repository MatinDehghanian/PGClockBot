"""UI polish 3.2.10 — mobile theme top air, wider force-join cards."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"


class MobileThemeTopAirTests(unittest.TestCase):
    def test_mobile_side_top_matches_theme_bottom(self):
        css = CSS.read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        # padding-top on .side equals .side-theme padding-bottom (--space-2)
        self.assertIn("padding-top: var(--space-2);", mobile.split(".side.open", 1)[0])
        theme = css.split(".side-theme {\n", 1)[1].split("}", 1)[0]
        self.assertIn("padding: 0 0 var(--space-2);", theme)


class ForceJoinWiderCardsTests(unittest.TestCase):
    def test_desktop_minmax_is_roomier(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(
            "grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));",
            css,
        )
        self.assertNotIn(
            "grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));",
            css,
        )


if __name__ == "__main__":
    unittest.main()
