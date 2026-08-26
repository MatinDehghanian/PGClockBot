"""Mobile sidebar — absolute fill inside shell, no calc dvh."""
from __future__ import annotations
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MobileSideFullHeightTests(unittest.TestCase):
    def test_side_absolute_top_bottom(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("position: absolute;", side)
        self.assertIn("bottom: 0;", side)
        self.assertNotIn("100dvh - var(--topbar-h)", side)
        self.assertNotIn("--safari-overlay", side)

    def test_closed_side_not_collapsed(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertNotIn("height: 0 !important;", mobile)


if __name__ == "__main__":
    unittest.main()
