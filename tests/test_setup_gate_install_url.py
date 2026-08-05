"""Setup gate URL at install / first-run."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.security_policy import is_public_ip


class SetupEntryUrlTests(unittest.TestCase):
    def test_build_setup_entry_url_includes_gate(self):
        from app.services import setup_wizard as sw

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            with (
                patch.object(sw, "DATA_DIR", data),
                patch.object(sw, "SETUP_GATE_FILE", data / "setup_gate.token"),
                patch.object(sw, "SETUP_FLAG", data / "setup_complete.flag"),
                patch.object(sw, "is_setup_complete", return_value=False),
                patch.object(sw, "default_panel_base_url", return_value="http://10.0.0.5:9000"),
            ):
                url = sw.build_setup_entry_url()
                self.assertIn("?gate=", url)
                self.assertTrue(url.startswith("http://10.0.0.5:9000/?gate="))

    def test_persist_writes_entry_file(self):
        from app.services import setup_wizard as sw

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            entry = data / "setup_entry.url"
            with (
                patch.object(sw, "DATA_DIR", data),
                patch.object(sw, "SETUP_GATE_FILE", data / "setup_gate.token"),
                patch.object(sw, "SETUP_ENTRY_FILE", entry),
                patch.object(sw, "SETUP_FLAG", data / "setup_complete.flag"),
                patch.object(sw, "is_setup_complete", return_value=False),
                patch.object(sw, "default_panel_base_url", return_value="http://srv:9000"),
            ):
                written = sw.persist_setup_entry_url()
                self.assertEqual(entry.read_text(encoding="utf-8").strip(), written)
                self.assertIn("?gate=", written)


class LocalClientTests(unittest.TestCase):
    def test_loopback_is_local(self):
        from app.services.setup_wizard import is_local_setup_client

        self.assertTrue(is_local_setup_client("127.0.0.1"))
        self.assertTrue(is_local_setup_client("::1"))
        self.assertFalse(is_public_ip("127.0.0.1"))

    def test_public_is_not_local(self):
        from app.services.setup_wizard import is_local_setup_client

        self.assertFalse(is_local_setup_client("8.8.8.8"))


class PgclockInstallHintTests(unittest.TestCase):
    def test_install_prints_setup_entry_url_helper(self):
        src = Path("pgclock.sh").read_text(encoding="utf-8")
        self.assertIn("setup_wizard_url", src)
        self.assertIn("setup_entry.url", src)
        self.assertIn("data/setup_gate.token", src)


if __name__ == "__main__":
    unittest.main()
