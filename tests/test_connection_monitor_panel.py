"""Bounded native subscription reads and live account ownership checks, offline."""

from __future__ import annotations

import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app.services.connection_monitor_panel import MonitorAccount, read_monitor_catalog
from app.services.pasarguard import PasarGuardClient, PasarGuardError


TOKEN = "synthetic-monitor-token-123456"


class MonitorPanelTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_account_identity_reads_native_routes_once(self) -> None:
        user = {"id": 900, "username": "monitor", "status": "active", "admin": {"username": "owner"},
                "used_traffic": 0, "data_limit": 0, "expire": None, "subscription_url": f"https://panel.example/sub/{TOKEN}"}
        account = MonitorAccount(900, hashlib.sha256(f"900:{TOKEN}".encode()).hexdigest(), "encrypted", "monitor")
        pg = SimpleNamespace(get_current_admin=AsyncMock(return_value={"role": {"id": 1, "is_owner": True}, "username": "owner"}),
                             get_user_by_id=AsyncMock(return_value=user), get_hosts=AsyncMock(return_value=[]),
                             get_inbounds_details=AsyncMock(return_value=[]), subscription_xray=AsyncMock(return_value=[]))
        with patch("app.services.connection_monitor_panel.get_pg", return_value=pg):
            with patch("app.services.connection_monitor_panel.reveal_monitor_token", AsyncMock(return_value=TOKEN)):
                result = await read_monitor_catalog(account)
        pg.subscription_xray.assert_awaited_once_with(TOKEN)
        self.assertEqual(result.native_configs, [])
        self.assertNotIn(TOKEN, repr(result))

    async def test_limited_panel_role_can_read_accessible_test_routes(self) -> None:
        user = {"id": 900, "username": "monitor", "status": "active", "admin": {"username": "owner"},
                "used_traffic": 0, "data_limit": 0, "expire": None, "subscription_url": f"https://panel.example/sub/{TOKEN}"}
        account = MonitorAccount(900, hashlib.sha256(f"900:{TOKEN}".encode()).hexdigest(), "encrypted", "monitor")
        admin = {"username": "owner", "is_owner": True, "is_sudo": True,
                 "role": {"id": 2, "is_owner": False, "permissions": {}}}
        pg = SimpleNamespace(get_current_admin=AsyncMock(return_value=admin), get_user_by_id=AsyncMock(return_value=user),
                             get_hosts=AsyncMock(return_value=[]), get_inbounds_details=AsyncMock(return_value=[]),
                             subscription_xray=AsyncMock(return_value=[]))
        with patch("app.services.connection_monitor_panel.get_pg", return_value=pg):
            with patch("app.services.connection_monitor_panel.reveal_monitor_token", AsyncMock(return_value=TOKEN)):
                result = await read_monitor_catalog(account)
        self.assertEqual(result.native_configs, [])
        pg.subscription_xray.assert_awaited_once_with(TOKEN)
        pg.get_current_admin.assert_not_awaited()

    async def test_native_routes_use_only_configured_panel_origin_and_no_authorization_header(self) -> None:
        requested = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(request)
            return httpx.Response(200, json=[{"outbounds": []}])

        pg = object.__new__(PasarGuardClient)
        pg.settings = SimpleNamespace(pg_subscription_path="/custom")
        pg.base_url = "https://panel.example/dashboard"
        pg._ensure_safe_target = AsyncMock()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            pg._client = client
            self.assertEqual(await pg.subscription_xray(TOKEN), [{"outbounds": []}])
        self.assertEqual(str(requested[0].url), f"https://panel.example/custom/{TOKEN}/xray")
        self.assertNotIn("Authorization", requested[0].headers)

    async def test_bad_native_payloads_and_errors_are_bounded_and_do_not_expose_token(self) -> None:
        payloads = (httpx.Response(302, headers={"Location": "https://external.example"}),
                    httpx.Response(403, text=TOKEN), httpx.Response(200, text=TOKEN),
                    httpx.Response(200, json={"secret": TOKEN}), httpx.Response(200, content=b"x" * (2*1024*1024+1)),
                    httpx.Response(200, text="[" * 2000 + "]" * 2000),
                    httpx.Response(200, json=[{}] * 1001))
        for response in payloads:
            pg = object.__new__(PasarGuardClient)
            pg.settings = SimpleNamespace(pg_subscription_path="/sub")
            pg.base_url = "https://panel.example"
            pg._ensure_safe_target = AsyncMock()
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as client:
                pg._client = client
                with self.subTest(status=response.status_code), self.assertRaises(PasarGuardError) as caught:
                    await pg.subscription_xray(TOKEN)
                self.assertNotIn(TOKEN, str(caught.exception))

    async def test_inactive_rotated_or_mismatched_account_never_reads_native_routes(self) -> None:
        user = {"id": 900, "username": "monitor", "status": "active", "admin": {"username": "owner"},
                "used_traffic": 0, "data_limit": 0, "expire": None, "subscription_url": f"https://panel.example/sub/{TOKEN}"}
        revision = hashlib.sha256(f"900:{TOKEN}".encode()).hexdigest()
        account = MonitorAccount(900, revision, "encrypted", "monitor")
        for changes in ({"status": "disabled"}, {"id": 901}, {"subscription_url": "https://panel.example/sub/rotated-monitor-token-123456"}):
            pg = SimpleNamespace(get_current_admin=AsyncMock(return_value={"role": {"id": 1, "is_owner": True}, "username": "owner"}),
                                 get_user_by_id=AsyncMock(return_value={**user, **changes}), get_hosts=AsyncMock(return_value=[]),
                                 get_inbounds_details=AsyncMock(return_value=[]), subscription_xray=AsyncMock(return_value=[]))
            with patch("app.services.connection_monitor_panel.get_pg", return_value=pg):
                with patch("app.services.connection_monitor_panel.reveal_monitor_token", AsyncMock(return_value=TOKEN)):
                    with self.subTest(changes=json.dumps(changes)), self.assertRaises(ValueError):
                        await read_monitor_catalog(account)
            pg.subscription_xray.assert_not_called()
