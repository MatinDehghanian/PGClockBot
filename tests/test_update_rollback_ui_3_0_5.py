"""Update rollback versions + redesigned update/force-join UI (3.0.5)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


class RecentVersionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_recent_from_releases(self):
        from app.services.updates import clear_update_cache, fetch_recent_versions

        clear_update_cache()
        payload = [
            {"tag_name": "v3.0.5", "name": "v3.0.5", "draft": False, "published_at": "2026-07-31T00:00:00Z"},
            {"tag_name": "v3.0.4", "name": "v3.0.4", "draft": False, "published_at": "2026-07-30T00:00:00Z"},
            {"tag_name": "v3.0.3", "name": "v3.0.3", "draft": False, "published_at": "2026-07-29T00:00:00Z"},
            {"tag_name": "v3.0.2", "name": "v3.0.2", "draft": False, "published_at": "2026-07-28T00:00:00Z"},
        ]

        class FakeResp:
            status_code = 200

            def json(self):
                return payload

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, url, **kwargs):
                return FakeResp()

        with patch("app.services.updates.httpx.AsyncClient", return_value=FakeClient()):
            rows = await fetch_recent_versions(limit=3, force=True)
        self.assertEqual([r["version"] for r in rows], ["3.0.5", "3.0.4", "3.0.3"])
        self.assertTrue(all(r["tag"].startswith("v") for r in rows))


class RollbackStartTests(unittest.TestCase):
    def test_rejects_version_outside_allowlist(self):
        from app.services.panel_update import start_rollback_to_version

        out = start_rollback_to_version("1.0.0", allowed=["3.0.5", "3.0.4", "3.0.3"])
        self.assertFalse(out["ok"])
        self.assertIn("۳ نسخه", out["error"])

    def test_rejects_current_version(self):
        from app.services.panel_update import start_rollback_to_version
        from app.version import __version__

        out = start_rollback_to_version(__version__, allowed=[__version__, "3.0.0", "2.9.0"])
        self.assertFalse(out["ok"])
        self.assertIn("همین الان", out["error"])


class UpdateUiSourceTests(unittest.TestCase):
    def test_update_page_has_rollback_select_no_terminal(self):
        src = Path("app/web/templates/_settings_update.html").read_text(encoding="utf-8")
        self.assertIn('id="rollback-version"', src)
        self.assertIn("settings-card", src)
        self.assertIn("progress-wrap", src)
        self.assertIn("rollback-row", src)
        self.assertIn('id="rollback-start"', src)
        self.assertIn("btn-danger", src)
        self.assertNotIn("update-details", src)
        self.assertNotIn("جزئیات عملیات", src)
        self.assertNotIn("روش جایگزین", src)
        self.assertNotIn("cmd-copy", src)

    def test_rollback_button_beside_select_is_danger(self):
        src = Path("app/web/templates/_settings_update.html").read_text(encoding="utf-8")
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn('class="rollback-row"', src)
        self.assertLess(src.find('id="rollback-version"'), src.find('id="rollback-start"'))
        btn = src.split('id="rollback-start"', 1)[0][-120:]
        self.assertIn("btn-danger", btn)
        self.assertIn(".rollback-row", css)
        self.assertIn(".rollback-field", css)
        self.assertIn("M4.5 6L8 3l3.5 3", css)
        self.assertIn("M4.5 10L8 13l3.5-3", css)

    def test_context_exposes_rollback_versions(self):
        src = Path("app/services/panel_update.py").read_text(encoding="utf-8")
        self.assertIn("fetch_recent_versions", src)
        self.assertIn("rollback_versions", src)
        self.assertIn("start_rollback_to_version", src)
        self.assertIn("_do_rollback_to_version", src)

    def test_force_channels_match_settings_pattern(self):
        html = Path("app/web/templates/_settings_field.html").read_text(encoding="utf-8")
        js = Path("app/web/static/panel.js").read_text(encoding="utf-8")
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn("force-channels-footer", html)
        self.assertIn("force-channel-fields", js)
        self.assertIn("force-channel-id-wrap", js)
        self.assertIn("btn-danger", js)
        self.assertIn(".force-channel-fields", css)
        self.assertIn(".force-channels-footer", css)


if __name__ == "__main__":
    unittest.main()
