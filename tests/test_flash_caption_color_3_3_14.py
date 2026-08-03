"""3.4.0 — flash captions inherit severity text color (from 3.3.14)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")


class FlashCaptionColorTests(unittest.TestCase):
    def test_muted_inside_flash_inherits(self):
        self.assertIn(".flash .muted,", CSS)
        self.assertIn(".flash .dash-bot-setup-inner .muted", CSS)
        # Shared inherit rule block
        block = CSS.split(".flash .muted,")[1].split("}")[0]
        self.assertIn("color: inherit", block)

    def test_dash_bot_setup_caption_inherits(self):
        block = CSS.split(".dash-bot-setup-inner .muted {")[1].split("}")[0]
        self.assertIn("color: inherit", block)
        self.assertNotIn("muted-fg", block)

    def test_home_update_caption_inherits(self):
        block = CSS.split(".home-update-copy .muted {")[1].split("}")[0]
        self.assertIn("color: inherit", block)

    def test_bot_setup_template_has_muted_caption(self):
        dash = (ROOT / "app/web/templates/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("flash err dash-bot-setup", dash)
        self.assertIn('class="muted"', dash)


class VersionBumpTests(unittest.TestCase):
    def test_version_at_least_3_4_0(self):
        from app.version import __version__

        self.assertGreaterEqual(tuple(int(x) for x in __version__.split(".")), (3, 4, 0))
        notes = (ROOT / "app/services/release_notes.py").read_text(encoding="utf-8")
        self.assertIn('"3.4.0"', notes)


if __name__ == "__main__":
    unittest.main()
