"""Short-page footer must not leave a flex-grown empty box above it."""
from __future__ import annotations
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class FooterFlexGapTests(unittest.TestCase):
    def test_main_body_not_flex_grow(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        # Content-sized main-body (no viewport-filling empty slab)
        block = css.split(".main-body {", 1)[1].split("}", 1)[0]
        self.assertIn("flex: 0 0 auto", block)
        self.assertNotIn("flex: 1 0 auto", block)
        foot = css.split(".site-footer {", 1)[1].split("}", 1)[0]
        self.assertIn("margin-top: 0", foot)
        self.assertNotIn("margin-top: auto", foot)

    def test_mobile_same(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".main-body { flex: 0 0 auto;", css)

if __name__ == "__main__":
    unittest.main()
