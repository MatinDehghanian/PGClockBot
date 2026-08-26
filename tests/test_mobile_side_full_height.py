"""Mobile sidebar — explicit 100dvh height (v8.2.12), full drawer to safe bottom."""
from __future__ import annotations
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MobileSideFullHeightTests(unittest.TestCase):
    def test_side_uses_explicit_dvh_height(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("height: calc(100dvh - var(--topbar-h) - var(--safe-top));", side)
        self.assertIn("max-height: calc(100dvh - var(--topbar-h) - var(--safe-top));", side)
        self.assertNotIn("bottom: var(--safari-overlay", side)
        self.assertNotIn("height: auto;", side)
        self.assertIn("overscroll-behavior-y: contain;", side)

    def test_closed_side_not_collapsed_to_zero_height(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertNotIn(".side:not(.open) {", mobile)
        self.assertIn("html.ios-safari .side:not(.open)", mobile)

    def test_backdrop_spans_full_viewport_bottom(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        back = css.split("/* Topbar + hamburger (mobile)", 1)[0]
        back = back.rsplit(".side-backdrop {", 1)[1].split("}", 1)[0]
        self.assertIn("bottom: 0;", back)
        self.assertNotIn("--safari-overlay", back)


if __name__ == "__main__":
    unittest.main()
