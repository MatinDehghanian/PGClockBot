"""3.2.19 — select caret inset matches title inset."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"


class SelectCaretPaddingTests(unittest.TestCase):
    def test_version_at_least_3_2_19(self):
        from app.services.release_notes import RELEASE_NOTES_FA
        from app.version import __version__

        self.assertGreaterEqual(tuple(int(x) for x in __version__.split(".")), (3, 2, 19))
        self.assertIn("3.2.19", RELEASE_NOTES_FA)

    def test_ui_select_symmetric_padding(self):
        css = CSS.read_text(encoding="utf-8")
        # Extract .ui-select-toggle block
        start = css.find(".ui-select-toggle {")
        self.assertGreater(start, 0)
        block = css[start : css.find("}", start)]
        self.assertIn("padding-inline-start: var(--space-2);", block)
        self.assertIn("padding-inline-end: var(--space-2);", block)
        self.assertNotIn("padding-inline-end: var(--space-4);", block)

    def test_ui_select_sm_symmetric_padding(self):
        css = CSS.read_text(encoding="utf-8")
        start = css.find(".ui-select-sm .ui-select-toggle,")
        self.assertGreater(start, 0)
        block = css[start : css.find("}", start)]
        self.assertIn("padding-inline-start: var(--space-1);", block)
        self.assertIn("padding-inline-end: var(--space-1);", block)
        self.assertNotIn("padding-inline-end: var(--space-3);", block)

    def test_native_select_caret_aligned(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("padding-inline-end: calc(var(--space-2) + 14px);", css)
        self.assertIn("background-position: left var(--space-2) center;", css)
        self.assertIn("padding-inline-end: calc(var(--space-1) + 12px);", css)


if __name__ == "__main__":
    unittest.main()
