"""3.3.0 — ticket modals portal to body like other panel modals."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_version_at_least_3_3_0(self):
        from app.services.release_notes import RELEASE_NOTES_FA
        from app.version import __version__

        self.assertGreaterEqual(tuple(int(x) for x in __version__.split(".")), (3, 3, 0))
        self.assertIn("3.3.0", RELEASE_NOTES_FA)


class ModalPortalTests(unittest.TestCase):
    def test_js_ports_ssr_open_modals(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("function ensureModalPorted", js)
        self.assertIn("document.querySelectorAll('.ui-modal.open')", js)
        self.assertIn("ensureModalPorted(el)", js)
        self.assertIn("data-modal-close-nav", js)
        self.assertIn("data-modal-escape-href", js)

    def test_tickets_use_shared_modal_behavior(self):
        src = (ROOT / "app/web/templates/tickets.html").read_text(encoding="utf-8")
        self.assertIn('id="modal-ticket-view"', src)
        self.assertIn('data-modal-escape-href="/tickets"', src)
        self.assertIn('data-modal-close-nav="/tickets"', src)
        # Inline modal bootstrap removed — panel.js owns portal/open
        self.assertNotIn("document.body.classList.add('modal-open')", src)
        self.assertNotIn("{% block head %}", src)


if __name__ == "__main__":
    unittest.main()
