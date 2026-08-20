"""Panel tickets UX 3.2.17 — no auto-modal from dashboard, nav dot, upload, dropup."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_version_at_least_3_2_17_notes(self):
        from app.services.release_notes import RELEASE_NOTES_FA
        from app.version import __version__

        self.assertGreaterEqual(tuple(int(x) for x in __version__.split(".")), (3, 2, 17))
        blob = " ".join(RELEASE_NOTES_FA["3.2.17"])
        self.assertIn("داشبورد", blob)
        self.assertIn("پیوست", blob)


class DashboardLinkTests(unittest.TestCase):
    def test_alert_href_is_list_only(self):
        src = (ROOT / "app/api/panel_tickets_pages.py").read_text(encoding="utf-8")
        self.assertIn('"href": "/tickets"', src)
        # Dashboard alert must not deep-link into modal via ?view=
        self.assertNotIn('href = f"/tickets?view=', src)
        self.assertNotIn('f"/tickets?view={tid}"', src)

    def test_templates_use_alert_href(self):
        # pg_home.html kept the dedicated ticket_alert banner (its own href).
        pg = (ROOT / "app/web/templates/pg_home.html").read_text(encoding="utf-8")
        self.assertIn('href="{{ ticket_alert.href }}"', pg)
        # reseller_home.html / home.html later generalized this into the
        # Action Center work-queue card, which renders each item's own href
        # (tickets is one of several entry kinds there) — see _home_ops.html.
        for name in ("_reseller_home_dash_body.html", "_home_dash_body.html"):
            src = (ROOT / "app/web/templates" / name).read_text(encoding="utf-8")
            self.assertIn('{% include "_home_ops.html" %}', src)
        ops = (ROOT / "app/web/templates/_home_ops.html").read_text(encoding="utf-8")
        self.assertIn('href="{{ item.href }}"', ops)


class NavDotTests(unittest.TestCase):
    def test_sidebar_dot_markup(self):
        base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
        self.assertIn("nav-dot", base)
        self.assertIn("tickets_unread", base)
        self.assertGreaterEqual(base.count("nav-dot"), 2)

    def test_nav_dot_css(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".nav-dot {", css)

    def test_owner_unread_model(self):
        src = (ROOT / "app/db/models.py").read_text(encoding="utf-8")
        self.assertIn("owner_unread", src)
        self.assertIn("attachment_path", src)


class DropupTests(unittest.TestCase):
    def test_row_actions_prefer_down_auto_flip(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("Prefer down when it fits", js)
        # Prefer below when it fits; flip up only when short
        self.assertIn("if (spaceBelow >= mh) openDown = true;", js)
        self.assertLess(
            js.find("if (spaceBelow >= mh) openDown = true;"),
            js.find("else if (spaceAbove >= mh) openDown = false;"),
        )


class UploadTests(unittest.TestCase):
    def test_forms_multipart(self):
        src = (ROOT / "app/web/templates/tickets.html").read_text(encoding="utf-8")
        self.assertIn('enctype="multipart/form-data"', src)
        self.assertIn('name="attachment"', src)
        # Attachments are served via authenticated route, not public /media/
        self.assertIn("/tickets/panel/", src)
        self.assertIn("/attachment/", src)
        self.assertNotIn("/media/", src)

    def test_service_helpers(self):
        from app.services.panel_tickets import ALLOWED_ATTACHMENT_EXT, MAX_ATTACHMENT_BYTES, sanitize_filename

        self.assertIn(".pdf", ALLOWED_ATTACHMENT_EXT)
        self.assertGreaterEqual(MAX_ATTACHMENT_BYTES, 1024 * 1024)
        self.assertEqual(sanitize_filename("../../evil.pdf"), "evil.pdf")


if __name__ == "__main__":
    unittest.main()
