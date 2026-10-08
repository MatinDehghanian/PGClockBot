"""Update channel (main/dev): normalize, URLs, migration preflight, version check."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.update_channel import (
    channel_label_fa,
    evaluate_migration_preflight,
    github_release_notes_url,
    github_version_url,
    normalize_channel,
    parse_revision_assignment,
)
from app.services.updates import check_github_update, clear_update_cache


class NormalizeChannelTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(normalize_channel("main"), "main")
        self.assertEqual(normalize_channel("stable"), "main")
        self.assertEqual(normalize_channel("DEV"), "dev")
        self.assertEqual(normalize_channel("develop"), "dev")
        self.assertEqual(normalize_channel(""), "main")
        self.assertEqual(normalize_channel(None), "main")
        self.assertEqual(normalize_channel("nope"), "main")

    def test_labels(self):
        self.assertEqual(channel_label_fa("main"), "پایدار")
        self.assertEqual(channel_label_fa("dev"), "توسعه")


class ChannelUrlTests(unittest.TestCase):
    def test_version_and_notes_urls(self):
        self.assertIn("/main/VERSION", github_version_url(channel="main"))
        self.assertIn("/dev/VERSION", github_version_url(channel="dev"))
        self.assertIn(
            "/dev/app/services/release_notes.py",
            github_release_notes_url(channel="dev"),
        )


class MigrationPreflightTests(unittest.TestCase):
    def test_ok_when_db_rev_on_remote(self):
        out = evaluate_migration_preflight(
            db_revision="0035_payment_review_messages",
            remote_revision_ids={"0034_service_automations", "0035_payment_review_messages"},
        )
        self.assertTrue(out["checked"])
        self.assertFalse(out["blocked"])
        self.assertEqual(out["tone"], "ok")

    def test_blocked_when_db_ahead_of_channel(self):
        out = evaluate_migration_preflight(
            db_revision="0035_payment_review_messages",
            remote_revision_ids={"0034_service_automations"},
        )
        self.assertTrue(out["checked"])
        self.assertTrue(out["blocked"])
        self.assertEqual(out["tone"], "err")
        self.assertIn("0035_payment_review_messages", out["message"])

    def test_warn_when_remote_unknown(self):
        out = evaluate_migration_preflight(
            db_revision="0035_payment_review_messages",
            remote_revision_ids=None,
        )
        self.assertFalse(out["checked"])
        self.assertFalse(out["blocked"])
        self.assertEqual(out["tone"], "warn")

    def test_parse_revision_assignment(self):
        src = 'revision = "0035_payment_review_messages"\ndown_revision = "0034"\n'
        self.assertEqual(
            parse_revision_assignment(src), "0035_payment_review_messages"
        )


class _FakeResp:
    def __init__(self, status_code: int, *, text: str = "", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data or {}

    def json(self):
        return self._json


class ChannelAwareUpdateCheckTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_update_cache()

    async def test_dev_uses_dev_version_url_not_releases(self):
        calls: list[str] = []

        async def fake_get(url, **kwargs):
            u = str(url)
            calls.append(u)
            if "VERSION" in u:
                return _FakeResp(200, text="9.9.9\n")
            return _FakeResp(404)

        client = MagicMock()
        client.get = AsyncMock(side_effect=fake_get)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.updates.httpx.AsyncClient", return_value=client), patch(
            "app.services.updates.local_version", return_value="0.2.0"
        ):
            info = await check_github_update(force=True, channel="dev")

        self.assertTrue(info["checked"])
        self.assertEqual(info["channel"], "dev")
        self.assertEqual(info["remote_version"], "9.9.9")
        self.assertTrue(info["update_available"])
        self.assertIn("توسعه", info["label"])
        self.assertIn("آپدیت", info["label"])
        self.assertTrue(any("/dev/VERSION" in u for u in calls))
        self.assertFalse(any("/releases/latest" in u for u in calls))

    async def test_dev_reports_no_update_when_already_latest(self):
        async def fake_get(url, **kwargs):
            if "VERSION" in str(url):
                return _FakeResp(200, text="0.2.21\n")
            return _FakeResp(404)

        client = MagicMock()
        client.get = AsyncMock(side_effect=fake_get)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.updates.httpx.AsyncClient", return_value=client), patch(
            "app.services.updates.local_version", return_value="0.2.21"
        ):
            info = await check_github_update(force=True, channel="dev")

        self.assertTrue(info["checked"])
        self.assertFalse(info["update_available"])
        self.assertIn("توسعه", info["label"])
        self.assertIn("نیست", info["label"])

    async def test_main_still_falls_back_to_releases(self):
        async def fake_get(url, **kwargs):
            u = str(url)
            if "VERSION" in u:
                raise RuntimeError("blocked")
            if u.endswith("/releases/latest"):
                return _FakeResp(200, json_data={"tag_name": "v3.2.2"})
            return _FakeResp(404)

        client = MagicMock()
        client.get = AsyncMock(side_effect=fake_get)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.updates.httpx.AsyncClient", return_value=client), patch(
            "app.services.updates.local_version", return_value="3.2.1"
        ):
            info = await check_github_update(force=True, channel="main")

        self.assertTrue(info["checked"])
        self.assertEqual(info["remote_version"], "3.2.2")
        self.assertEqual(info["channel"], "main")


if __name__ == "__main__":
    unittest.main()
