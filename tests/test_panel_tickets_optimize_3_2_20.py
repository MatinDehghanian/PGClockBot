"""3.2.20 — panel ticket cleanup and load optimizations."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_version(self):
        from app.version import __version__

        self.assertEqual(__version__, "3.2.20")
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "3.2.20")

    def test_notes(self):
        from app.services.release_notes import RELEASE_NOTES_FA

        blob = " ".join(RELEASE_NOTES_FA["3.2.20"])
        self.assertIn("تیکت", blob)


class DeadCodeRemovedTests(unittest.TestCase):
    def test_unused_helpers_gone(self):
        src = (ROOT / "app/services/panel_tickets.py").read_text(encoding="utf-8")
        self.assertNotIn("def first_answered_unread_id", src)
        self.assertNotIn("def count_owner_waiting", src)
        self.assertNotIn("def enrich_opener_label", src)
        self.assertNotIn("def status_label", src)
        self.assertNotIn("def priority_label", src)
        self.assertNotIn("ResellerProfile", src)
        self.assertNotIn("OWNER_STATUSES", src)

    def test_list_does_not_eager_load_messages(self):
        src = (ROOT / "app/services/panel_tickets.py").read_text(encoding="utf-8")
        # selectinload only in get_ticket path
        self.assertIn("selectinload(PanelTicket.messages)", src)
        self.assertEqual(src.count("selectinload(PanelTicket.messages)"), 1)
        list_fn = src[src.find("async def list_tickets") : src.find("async def get_ticket")]
        self.assertNotIn("selectinload", list_fn)


class PollSkipTests(unittest.TestCase):
    def test_skip_paths(self):
        from app.services.panel_tickets import SKIP_UNREAD_PATHS

        self.assertIn("/home/metrics", SKIP_UNREAD_PATHS)
        self.assertIn("/update/status", SKIP_UNREAD_PATHS)
        self.assertIn("/settings/ssl/progress", SKIP_UNREAD_PATHS)

    def test_require_staff_skips_polls(self):
        app_src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("SKIP_UNREAD_PATHS", app_src)


class UnreadReuseTests(unittest.TestCase):
    def test_dashboard_alert_accepts_unread(self):
        src = (ROOT / "app/api/panel_tickets_pages.py").read_text(encoding="utf-8")
        self.assertIn("unread: int | None = None", src)
        self.assertIn("unread_from_tickets", src)
        home = (ROOT / "app/api/home_pages.py").read_text(encoding="utf-8")
        self.assertIn("panel_tickets_unread", home)
        pg = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn("panel_tickets_unread", pg)

    def test_unread_from_tickets(self):
        from app.services.panel_tickets import unread_from_tickets

        rows = [
            SimpleNamespace(owner_unread=True, answered_unread=False),
            SimpleNamespace(owner_unread=True, answered_unread=True),
            SimpleNamespace(owner_unread=False, answered_unread=True),
        ]
        self.assertEqual(unread_from_tickets(rows, {"role": "admin"}), 2)
        self.assertEqual(
            unread_from_tickets(rows, {"role": "reseller", "bot_user_id": 1}),
            2,
        )


class MarkViewedSignatureTests(unittest.TestCase):
    def test_pages_pass_ticket_object(self):
        src = (ROOT / "app/api/panel_tickets_pages.py").read_text(encoding="utf-8")
        self.assertIn("await mark_viewed(session, staff, active_ticket)", src)
        self.assertNotIn("mark_viewed(session, staff, int(view))", src)


if __name__ == "__main__":
    unittest.main()
