"""Ticket close/status actions — shared layout for panel + Telegram modals."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TicketCloseModalLayoutTests(unittest.TestCase):
    def test_shared_close_form_and_titles(self):
        src = (ROOT / "app/web/templates/tickets.html").read_text(encoding="utf-8")
        self.assertEqual(src.count("ticket-close-form"), 2)
        self.assertIn('data-confirm-title="بستن تیکت"', src)
        self.assertNotIn("بستن تیکت ربات", src)
        # Telegram: close only, no status select
        tg = src[src.find("modal-tg-ticket-view") :]
        self.assertIn("ticket-close-form", tg)
        self.assertNotIn("ticket-status-form", tg)
        self.assertNotIn("ذخیره وضعیت", tg)

    def test_css_left_align_and_mobile_full_width(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".ticket-close-form", css)
        self.assertIn("margin-inline-start: auto", css)
        # Desktop base: pin actions to the inline-end (left in RTL)
        base = css.split(".ticket-closed-note", 1)[1].split("html[data-theme=\"light\"] .ticket-thread", 1)[0]
        self.assertIn("justify-content: flex-end", base)
        self.assertIn(".ticket-close-form", base)
        # Mobile full-width close + status buttons
        self.assertIn(".ticket-close-form > .btn", css)
        mob = css[css.find(".ticket-close-form > .btn") : css.find(".ticket-close-form > .btn") + 200]
        self.assertIn("width: 100%", mob)


if __name__ == "__main__":
    unittest.main()
