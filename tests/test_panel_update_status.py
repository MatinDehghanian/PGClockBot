"""Tests for clearing stale panel update progress UI."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import panel_update as pu


class StaleUpdateStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.status = Path(self.tmp.name) / "panel_update.json"
        self.patches = [
            patch.object(pu, "STATUS_FILE", self.status),
            patch.object(pu, "DATA_DIR", Path(self.tmp.name)),
            patch.object(pu, "local_version", return_value="1.7.33"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _write(self, data: dict):
        self.status.write_text(json.dumps(data), encoding="utf-8")

    def test_clear_idle_wipes_awaiting_restart(self):
        self._write(
            {
                "state": "done",
                "awaiting_restart": True,
                "to_version": "1.7.30",
                "log": ["x"],
                "step_key": "restart",
                "percent": 98,
            }
        )
        out = pu.clear_idle_status()
        self.assertEqual(out["state"], "idle")
        self.assertFalse(out.get("awaiting_restart"))
        self.assertEqual(out.get("log"), [])
        disk = json.loads(self.status.read_text(encoding="utf-8"))
        self.assertFalse(disk.get("awaiting_restart"))

    def test_resolve_clears_when_local_already_at_target(self):
        self._write(
            {
                "state": "done",
                "awaiting_restart": True,
                "to_version": "1.7.30",
                "log": ["waiting"],
                "step_key": "restart",
                "message": "منتظر قطع شدن سرویس قبلی",
                "percent": 98,
            }
        )
        out = pu.resolve_stale_update_status()
        self.assertEqual(out["state"], "idle")
        self.assertFalse(out.get("awaiting_restart"))

    def test_resolve_keeps_awaiting_when_target_newer(self):
        self._write(
            {
                "state": "done",
                "awaiting_restart": True,
                "to_version": "9.9.9",
                "log": ["waiting"],
                "step_key": "restart",
            }
        )
        out = pu.resolve_stale_update_status()
        self.assertTrue(out.get("awaiting_restart"))
        self.assertEqual(out["state"], "done")

    def test_resolve_keeps_running(self):
        self._write({"state": "running", "awaiting_restart": False, "step_key": "pull"})
        out = pu.resolve_stale_update_status()
        self.assertEqual(out["state"], "running")


if __name__ == "__main__":
    unittest.main()
