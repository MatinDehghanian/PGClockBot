"""Web connection tests share bot rules, isolate shops and keep secrets private."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from connection_monitor_support import MonitorDatabaseCase, OWNER_STAFF

from app.api.app import create_api_app, render
from app.api.connection_status_pages import register_connection_status_pages
from app.db.models import ConnectionMonitorSnapshot, ConnectionMonitorState, ConnectionMonitorTarget, OrgPrincipal, UserService
from app.services.connection_monitor_settings import set_monitor_account
from app.services.connection_monitor_preferences import pause_monitor_target, save_monitor_preferences
from app.services.connection_monitor_access import MonitorAccess
from app.services.connection_monitor_accounts import ACCOUNT_MESSAGES
from app.services.connection_monitor_preferences import MonitorPreferences
from app.services.connection_status import public_connection_page
from app.services.connection_status_texts import LEGACY_MONITOR_TEXTS, MONITOR_TEXT_DEFAULTS
from app.services.users import clear_settings_cache, get_all_settings, set_settings_bulk


TOKEN = "synthetic-monitor-token-123456"


class MonitorWebTests(MonitorDatabaseCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.staff = dict(OWNER_STAFF)
        fixture = json.loads((Path(__file__).parent / "fixtures/connection_monitor_catalog.json").read_text())
        self.panel = SimpleNamespace(
            get_current_admin=AsyncMock(side_effect=AssertionError("Owner API must not be called")),
            get_user_by_username=AsyncMock(return_value={
                "id": 900, "username": "Monitor-Only", "status": "active", "admin": None,
                "used_traffic": 0, "data_limit": 0, "expire": None,
                "subscription_url": f"https://panel.example/sub/{TOKEN}",
            }),
            get_user_by_id=AsyncMock(), get_hosts=AsyncMock(return_value=fixture["hosts"]),
            get_inbounds_details=AsyncMock(return_value=fixture["inbounds"]),
            subscription_xray=AsyncMock(return_value=fixture["native_configs"]),
        )
        self.panel.get_user_by_id.return_value = self.panel.get_user_by_username.return_value
        for patcher in (
            patch("app.services.connection_monitor_accounts.get_pg", return_value=self.panel),
            patch("app.services.connection_monitor_panel.get_pg", return_value=self.panel),
            patch("app.services.secret_box._root_secret", return_value=b"synthetic-test-root-never-production"),
            patch("app.services.connection_monitor_admin.XrayBinary.verify", return_value=Path("/synthetic/xray")),
            patch("app.api.connection_status_pages.get_settings", return_value=SimpleNamespace(
                connection_monitor_xray_path="/synthetic/xray", connection_monitor_xray_sha256="a" * 64)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        async def get_db() -> AsyncIterator[AsyncSession]:
            async with self.Session() as session:
                yield session

        self.app = FastAPI()
        register_connection_status_pages(self.app, render=render, require_staff=lambda: self.staff, get_db=get_db)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")
        clear_settings_cache()
        self.addCleanup(clear_settings_cache)

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        await super().asyncTearDown()

    async def attach(self) -> None:
        response = await self.client.post("/connection-status/account", data={"username": "monitor-only"})
        self.assertEqual(response.status_code, 303, response.text)
        self.assertNotIn("error=", response.headers["location"])

    async def select_host(self) -> int:
        await self.attach()
        response = await self.client.post("/connection-status/hosts/41")
        self.assertEqual(response.status_code, 303)
        self.assertNotIn("error=", response.headers["location"])
        async with self.Session() as session:
            return await session.scalar(select(ConnectionMonitorTarget.id))

    async def test_active_hosts_load_after_the_panel_regenerates_the_same_users_link(self) -> None:
        await self.attach()
        self.panel.get_user_by_id.return_value = {
            **self.panel.get_user_by_username.return_value,
            "subscription_url": "https://panel.example/sub/newly-issued-token-123456",
        }
        response = await self.client.get("/connection-status?hosts=1")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(ACCOUNT_MESSAGES["account_changed"], response.text)
        self.assertIn("نام متغیر {USERNAME}", response.text)
        self.panel.subscription_xray.assert_awaited_once_with(TOKEN)
        self.assertNotIn(TOKEN, response.text)

    async def test_empty_page_has_setup_actions_without_panel_calls_or_secrets(self) -> None:
        response = await self.client.get("/connection-status")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("تنظیم Test user", response.text)
        self.assertIn("شروع تست‌ها", response.text)
        self.assertIn("داخل ایران", response.text)
        self.assertIn('href="/connection-status"', response.text)
        self.assertIn('name="csrf_token"', response.text)
        self.assertIn("هنوز هاستی", response.text)
        self.panel.get_current_admin.assert_not_called()
        self.panel.get_hosts.assert_not_called()
        self.panel.get_user_by_username.assert_not_called()
        self.assertNotIn(TOKEN, response.text)

    async def test_register_select_publish_queue_and_pause_use_the_shared_services(self) -> None:
        target_id = await self.select_host()
        response = await self.client.get("/connection-status?hosts=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("هاست‌های فعال پنل", response.text)
        self.panel.subscription_xray.assert_awaited()
        response = await self.client.post("/connection-status/runtime", data={"enabled": "1"})
        self.assertNotIn("error=", response.headers["location"])
        hostile_name = '<script>alert("host")</script>'
        response = await self.client.post(f"/connection-status/targets/{target_id}", data={
            "public_name": hostile_name, "display_order": "7", "is_public": "1", "host_id": "72", "shop_id": "2",
        })
        self.assertNotIn("error=", response.headers["location"])
        async with self.Session() as session:
            target = await session.get(ConnectionMonitorTarget, target_id)
            self.assertEqual((target.pg_host_id, target.reseller_id, target.public_name, target.display_order, target.is_public),
                             (41, None, hostile_name, 7, True))
            state = await session.scalar(select(ConnectionMonitorState))
            state.catalog_synced_at = self.now
            for row in (await session.scalars(select(ConnectionMonitorSnapshot))).all():
                row.status, row.checked_at, row.delay_ms = "healthy", self.now, 123
            await session.commit()
            public = await public_connection_page(session, now=self.now)
            self.assertEqual(public.entries[0].public_name, hostile_name)
        before_calls = self.panel.get_hosts.await_count
        response = await self.client.get("/connection-status")
        self.assertEqual(self.panel.get_hosts.await_count, before_calls)
        self.assertIn("&lt;script&gt;", response.text)
        self.assertNotIn(hostile_name, response.text)
        self.assertNotIn(TOKEN, response.text)
        self.assertIn("Real delay", response.text)
        self.assertNotIn("منقضی", response.text)
        response = await self.client.post(f"/connection-status/targets/{target_id}/check")
        self.assertNotIn("error=", response.headers["location"])
        async with self.Session() as session:
            self.assertTrue((await session.get(ConnectionMonitorTarget, target_id)).manual_pending)
        self.assertEqual(self.panel.get_hosts.await_count, before_calls)
        response = await self.client.post(f"/connection-status/targets/{target_id}/pause")
        self.assertNotIn("error=", response.headers["location"])
        async with self.Session() as session:
            target = await session.get(ConnectionMonitorTarget, target_id)
            self.assertFalse(target.test_enabled)
            self.assertFalse(target.is_public)

    async def test_private_name_can_be_empty_and_publication_without_name_is_rejected_atomically(self) -> None:
        target_id = await self.select_host()
        response = await self.client.post(f"/connection-status/targets/{target_id}", data={
            "public_name": "", "display_order": "5", "is_public": "0",
        })
        self.assertNotIn("error=", response.headers["location"])
        response = await self.client.post(f"/connection-status/targets/{target_id}", data={
            "public_name": "", "display_order": "9", "is_public": "1",
        })
        self.assertIn("error=", response.headers["location"])
        async with self.Session() as session:
            target = await session.get(ConnectionMonitorTarget, target_id)
            self.assertEqual((target.display_order, target.public_name, target.is_public), (5, "", False))

    async def test_a_stale_edit_form_cannot_restart_a_host_paused_during_the_request(self) -> None:
        target_id = await self.select_host()

        async def pause_before_save(session: AsyncSession, access: MonitorAccess, preferences: MonitorPreferences,
                                    *, expected_target_id: int | None = None) -> int:
            async with self.Session() as other:
                await pause_monitor_target(other, access, target_id=target_id)
            return await save_monitor_preferences(session, access, preferences, expected_target_id=expected_target_id)

        with patch("app.services.connection_monitor_actions.save_monitor_preferences", side_effect=pause_before_save):
            response = await self.client.post(f"/connection-status/targets/{target_id}", data={
                "public_name": "stale edit", "display_order": "9", "is_public": "0",
            })
        self.assertIn("error=", response.headers["location"])
        async with self.Session() as session:
            target = await session.get(ConnectionMonitorTarget, target_id)
            self.assertEqual((target.test_enabled, target.is_public, target.public_name), (False, False, ""))

    async def test_reseller_customer_legacy_admin_and_disabled_owner_cannot_read_or_mutate(self) -> None:
        for staff in ({"role": "reseller", "bot_user_id": 2, "permissions": ["connection_status_manage"]},
                      {"role": "user", "bot_user_id": 4}, {"role": "admin"},
                      {**OWNER_STAFF, "org_status": "disabled"}):
            self.staff.clear()
            self.staff.update(staff)
            for path, data in (("/connection-status/account", {"username": "monitor-only"}),
                               ("/connection-status/runtime", {"enabled": "1"}), ("/connection-status/hosts/41", {}),
                               ("/connection-status/targets/1/check", {}), ("/connection-status/targets/1/pause", {}),
                               ("/connection-status/targets/1", {"public_name": "x", "display_order": "0", "is_public": "0"})):
                with self.subTest(staff=staff, path=path):
                    self.assertEqual((await self.client.post(path, data=data)).status_code, 403)
            self.assertEqual((await self.client.get("/connection-status?hosts=1")).status_code, 403)
        self.panel.get_hosts.assert_not_called()
        self.panel.get_user_by_username.assert_not_called()

    async def test_other_shop_target_cannot_be_edited_or_checked_by_id(self) -> None:
        await self.attach()
        async with self.Session() as session:
            session.add(ConnectionMonitorTarget(id=999, reseller_id=2, pg_host_id=41, test_enabled=True, public_name="other"))
            await session.commit()
        for suffix, data in (("", {"public_name": "changed", "display_order": "1", "is_public": "0"}),
                             ("/pause", {}), ("/check", {})):
            response = await self.client.post("/connection-status/targets/999" + suffix, data=data)
            self.assertIn("error=", response.headers["location"])
        async with self.Session() as session:
            target = await session.get(ConnectionMonitorTarget, 999)
            self.assertEqual((target.public_name, target.test_enabled, target.is_public), ("other", True, False))

    async def test_panel_failure_keeps_local_status_and_returns_safe_errors(self) -> None:
        await self.select_host()
        self.panel.get_hosts.side_effect = httpx.ConnectError(TOKEN)
        response = await self.client.get("/connection-status?hosts=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ارتباط با پنل برقرار نشد", response.text)
        self.assertIn("Real delay", response.text)
        self.assertNotIn(TOKEN, response.text)

    async def test_invalid_values_are_rejected_without_partial_edits(self) -> None:
        target_id = await self.select_host()
        for value in ("-1", "2147483648", "nan", "true", "1.5"):
            response = await self.client.post(f"/connection-status/targets/{target_id}", data={
                "public_name": "changed", "display_order": value, "is_public": "0",
            })
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual((await self.client.get("/connection-status?after=-1")).status_code, 422)
        async with self.Session() as session:
            self.assertEqual((await session.get(ConnectionMonitorTarget, target_id)).public_name, "")

    async def test_missing_core_configuration_disables_start_but_keeps_settings_visible(self) -> None:
        await self.attach()
        with patch("app.api.connection_status_pages.get_settings", return_value=SimpleNamespace(
            connection_monitor_xray_path="", connection_monitor_xray_sha256="")):
            response = await self.client.get("/connection-status")
        self.assertEqual(response.status_code, 200)
        self.assertIn("CONNECTION_MONITOR_XRAY_PATH", response.text)
        self.assertIn('disabled>شروع تست‌ها', response.text)

    async def test_web_rechecks_owner_after_the_panel_request(self) -> None:
        async def revoke(_username: str) -> dict[str, object]:
            async with self.Session() as session:
                owner = await session.get(OrgPrincipal, 1)
                owner.status = "disabled"
                await session.commit()
            return self.panel.get_user_by_id.return_value
        self.panel.get_user_by_username.side_effect = revoke
        response = await self.client.post("/connection-status/account", data={"username": "monitor-only"})
        self.assertIn("error=", response.headers["location"])
        async with self.Session() as session:
            self.assertIsNone((await session.scalar(select(ConnectionMonitorState))).pg_user_id)

    async def test_customer_test_user_is_rejected_with_an_actionable_error(self) -> None:
        async with self.Session() as session:
            session.add(UserService(bot_user_id=5, pg_user_id=900, pg_username="Monitor-Only", remark="customer"))
            await session.commit()
        response = await self.client.post("/connection-status/account", data={"username": "monitor-only"})
        response = await self.client.get(response.headers["location"])
        self.assertIn("یک user جدا", response.text)
        self.assertNotIn(TOKEN, response.text)

    async def test_pasting_a_long_subscription_link_never_echoes_it_in_validation_errors(self) -> None:
        response = await self.client.post("/connection-status/account", data={
            "username": f"https://panel.example/sub/{TOKEN}" + "x" * 128,
        })
        self.assertNotIn(TOKEN, response.text)
        self.assertEqual(response.status_code, 303)
        self.assertNotIn(TOKEN, response.headers["location"])
        self.panel.get_user_by_username.assert_not_awaited()

    async def test_old_default_texts_are_readable_and_custom_settings_are_preserved(self) -> None:
        async with self.Session() as session:
            await set_settings_bulk(session, {**LEGACY_MONITOR_TEXTS, "menu_order": "shop,services", "connection_status_name_prompt": "نام دلخواه"})
            ui = await get_all_settings(session)
            self.assertEqual(ui["connection_status_account_prompt"], MONITOR_TEXT_DEFAULTS["connection_status_account_prompt"])
            self.assertEqual(ui["connection_status_name_prompt"], "نام دلخواه")
            self.assertEqual(ui["menu_order"], "shop,services")

    async def test_existing_test_user_can_be_registered_again_without_panel_owner_access(self) -> None:
        async with self.Session() as session:
            await set_monitor_account(session, self.access, username="monitor-only")
        await self.attach()
        async with self.Session() as session:
            self.assertEqual((await session.scalar(select(ConnectionMonitorState))).pg_username, "Monitor-Only")
        self.panel.get_current_admin.assert_not_awaited()

    async def test_real_panel_middleware_rejects_missing_csrf_and_accepts_the_valid_form(self) -> None:
        with patch("app.api.app.DATA_DIR", Path(self.temporary.name)):
            app = create_api_app()
        route = next(route for route in app.routes if getattr(route, "path", None) == "/connection-status")
        dependencies = list(route.dependant.dependencies)
        while dependencies:
            dependency = dependencies.pop()
            if dependency.call.__name__ == "require_staff":
                app.dependency_overrides[dependency.call] = lambda: self.staff
            elif dependency.call.__name__ == "get_db":
                async def get_db() -> AsyncIterator[AsyncSession]:
                    async with self.Session() as session:
                        yield session
                app.dependency_overrides[dependency.call] = get_db
            dependencies.extend(dependency.dependencies)
        with patch("app.api.app.is_setup_complete", return_value=True):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                         cookies={"session": "synthetic-session", "csrf": "synthetic-csrf"}) as client:
                denied = await client.post("/connection-status/account", data={"username": "monitor-only"}, headers={"Origin": "http://test"})
                self.assertEqual(denied.status_code, 403)
                self.panel.get_user_by_username.assert_not_awaited()
                accepted = await client.post("/connection-status/account", data={
                    "username": "monitor-only", "csrf_token": "synthetic-csrf",
                }, headers={"Origin": "http://test"})
        self.assertEqual(accepted.status_code, 303, accepted.text)
        self.assertNotIn("error=", accepted.headers["location"])
