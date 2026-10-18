"""Status grouping and read-only service previews preserve shop/customer scope."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.user_service_preview_pages import register_user_service_preview_pages
from app.db import Base
from app.db.models import BotUser, BotUserShop, UserService
from app.services.formatting import format_money, format_number
from app.services.service_live_info import service_info_error
from app.services.service_status import SERVICE_STATUSES
from app.services.shop_scope import ShopScopeError
from app.services.user_service_preview import ServicePreview, load_user_service_preview
from app.services.users_ops import (
    UserOpsRow, build_user_ops_row, build_users_ops_page, filter_ops_rows, summarize_ops_counts, users_list_href,
)

SHOP = {"role": "reseller", "bot_user_id": 5, "permissions": ["dashboard"]}
OWNER = {"role": "admin", "org_principal_id": 1, "org_depth": 0, "org_parent_id": None, "org_status": "active"}
HOSTILE = '<img src=x onerror="alert(1)">'


class ServiceStatusTests(unittest.TestCase):
    def row(self, statuses: list[str | None], *, blocked: bool = False) -> UserOpsRow:
        now = datetime.now(timezone.utc)
        services = [SimpleNamespace(
            id=i + 1, pg_username=f"service{i}", plan=None, created_at=now,
            quota_synced_at=now, quota_expire_at=now + timedelta(days=1), quota_status=status,
        ) for i, status in enumerate(statuses)]
        return build_user_ops_row(SimpleNamespace(id=1, is_blocked=blocked), services, now=now)

    def test_each_panel_status_is_a_filter(self) -> None:
        for status in SERVICE_STATUSES:
            with self.subTest(status=status.key):
                row = self.row([status.key])
                self.assertEqual(filter_ops_rows([row], status.key), [row])
                self.assertEqual(summarize_ops_counts([row])[status.key], 1)
                self.assertEqual(users_list_href(filter_key=status.key), f"/users?filter={status.key}")

    def test_multiple_services_count_the_customer_once_per_status(self) -> None:
        row = self.row(["active", "active", "expired"])
        counts = summarize_ops_counts([row])
        self.assertEqual((counts["active"], counts["expired"], counts["total"]), (1, 1, 1))
        self.assertEqual(filter_ops_rows([row], "expired"), [row])
        self.assertEqual(len(row.services), 3)
        self.assertEqual(row.status_counts, {"active": 2, "expired": 1})

    def test_unknown_status_does_not_look_active_and_blocking_is_separate(self) -> None:
        row = self.row([None, "future_status"], blocked=True)
        self.assertEqual(filter_ops_rows([row], "active"), [])
        self.assertEqual(filter_ops_rows([row], "unknown"), [row])
        self.assertEqual(filter_ops_rows([row], "blocked"), [row])
        self.assertEqual(filter_ops_rows([self.row([])], "unknown"), [])

    def test_on_hold_is_not_reported_as_an_expiring_service(self) -> None:
        row = self.row(["on-hold"])
        self.assertFalse(row.expiring)
        self.assertEqual(row.expire_text, "پس از اولین اتصال")
        self.assertIsNone(row.days_left)


class ServiceBrowserRenderingTests(unittest.TestCase):
    def test_customer_expands_to_escaped_services_and_individual_previews(self) -> None:
        env = Environment(loader=ChoiceLoader([
            DictLoader({"base.html": "{% block content %}{% endblock %}"}),
            FileSystemLoader(Path(__file__).resolve().parents[1] / "app/web/templates"),
        ]), autoescape=True)
        env.filters.update(num=format_number, money=format_money)
        now = datetime.now(timezone.utc)
        user = SimpleNamespace(
            id=7, telegram_id=7, full_name=HOSTILE, username="customer", is_demo=False,
            role="user", color_tag=None, is_blocked=True,
        )
        services = [SimpleNamespace(
            id=sid, pg_username=HOSTILE if sid == 11 else "pending-service", plan=None,
            created_at=now, quota_status=status,
        ) for sid, status in ((11, "active"), (12, "on_hold"))]
        row = build_user_ops_row(user, services, now=now)
        rendered = env.get_template("users.html").render(
            rows=[row], filter="active", counts=summarize_ops_counts([row]),
            filter_href=users_list_href, service_statuses=SERVICE_STATUSES,
            can_manage_users=False, can_provision_users=False,
            can_user_ops=False, can_edit_user_services=False,
        )
        self.assertIn('<details class="users-services"', rendered)
        self.assertIn('<ul class="users-service-list">', rendered)
        self.assertIn('/users/7/services/11/preview', rendered)
        self.assertIn('/users/7/services/12/preview', rendered)
        self.assertIn('dir="ltr">&lt;img', rendered)
        self.assertIn('در انتظار اتصال', rendered)
        self.assertIn('پس از اولین اتصال', rendered)
        self.assertIn('aria-current="page"', rendered)
        self.assertIn('وضعیت سرویس‌ها', rendered)
        self.assertIn('مسدود در بات', rendered)
        self.assertNotIn(HOSTILE, rendered)
        self.assertNotIn('/users/7/delete', rendered)
        self.assertNotIn('/users/7/block', rendered)
        self.assertNotIn('users-svc-select', rendered)


class ServicePreviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.Session() as session:
            session.add_all([
                BotUser(id=5, telegram_id=5, referral_code="shop", role="reseller"),
                BotUser(id=6, telegram_id=6, referral_code="shop2", role="reseller"),
                BotUser(id=7, telegram_id=7, referral_code="customer", reseller_id=5),
                BotUser(id=8, telegram_id=8, referral_code="customer2", reseller_id=6),
            ])
            await session.flush()
            session.add(BotUserShop(bot_user_id=7, shop_id=None))
            for sid, uid, shop, review, status in (
                (11, 7, 5, False, "active"), (12, 7, None, False, "expired"),
                (13, 8, 6, False, "disabled"), (14, 7, 5, True, "limited"),
            ):
                session.add(UserService(
                    id=sid, bot_user_id=uid, shop_id=shop, shop_needs_review=review,
                    pg_user_id=sid, pg_username=HOSTILE if sid == 11 else f"service{sid}",
                    subscription_token="secret-token", subscription_url="https://example.test/sub/secret",
                    quota_status=status, quota_data_limit_bytes=1024**3,
                    quota_expire_at=datetime.now(timezone.utc) + timedelta(days=2),
                    quota_synced_at=datetime.now(timezone.utc),
                ))
            await session.commit()
        self.fetch = AsyncMock(return_value={
            "status": "active", "data_limit": 1024**3, "used_traffic": 512 * 1024**2, "expire": 0,
            "subscription_url": "secret-url", "password": "secret-password",
        })
        patcher = patch("app.services.user_service_preview.fetch_subscription_info", self.fetch)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def preview(self, staff: dict = SHOP, *, customer: int = 7, service: int = 11) -> ServicePreview:
        async with self.Session() as session:
            return await load_user_service_preview(session, staff, customer_id=customer, service_id=service)

    async def test_live_preview_is_whitelisted_and_transaction_ends_before_panel_call(self) -> None:
        async with self.Session() as session:
            async def fetch(*args, **kwargs) -> dict:
                self.assertFalse(session.in_transaction())
                return self.fetch.return_value
            self.fetch.side_effect = fetch
            result = await load_user_service_preview(session, SHOP, customer_id=7, service_id=11)
        self.assertEqual(result.username, HOSTILE)
        self.assertEqual(result.status, "active")
        self.assertIn("مگ", result.used)
        self.assertEqual(result.expire, "نامحدود")
        self.assertEqual(result.source, "اطلاعات زنده از پاسارگارد")

    async def test_wrong_shop_customer_or_review_service_never_contacts_panel(self) -> None:
        for staff, uid, sid in (
            (SHOP, 7, 12), (SHOP, 8, 13), (SHOP, 8, 11), (SHOP, 7, 14),
            ({**SHOP, "bot_user_id": 6}, 7, 11), (OWNER, 7, 11),
        ):
            with self.subTest(staff=staff, uid=uid, sid=sid), self.assertRaises(ValueError):
                await self.preview(staff, customer=uid, service=sid)
        self.fetch.assert_not_awaited()

    async def test_missing_permission_denies_preview(self) -> None:
        with self.assertRaises(PermissionError):
            await self.preview({**SHOP, "permissions": []})
        self.fetch.assert_not_awaited()

    async def test_an_admin_without_owner_or_shop_scope_is_denied(self) -> None:
        with self.assertRaises(ShopScopeError):
            await self.preview({"role": "admin"})
        self.fetch.assert_not_awaited()

    async def test_platform_preview_supports_a_customer_who_also_belongs_to_a_shop(self) -> None:
        result = await self.preview(OWNER, service=12)
        self.assertEqual(result.username, "service12")

    async def test_invalid_record_ids_are_rejected_before_querying(self) -> None:
        for value in (True, -1, 0, 2**31, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                await self.preview(service=value)
        self.fetch.assert_not_awaited()

    async def test_on_hold_preview_shows_duration_after_connection(self) -> None:
        self.fetch.return_value = {
            "status": "on_hold", "expire": 0, "expire_duration": 30 * 86400,
            "used_traffic": 0, "data_limit": 0,
        }
        result = await self.preview()
        self.assertEqual(result.status, "on_hold")
        self.assertIn("پس از اتصال", result.expire)
        self.assertEqual(result.remaining, "نامحدود")

    async def test_timeout_keeps_cached_status_and_quota(self) -> None:
        self.fetch.return_value = service_info_error("timeout")
        result = await self.preview()
        self.assertEqual(result.status, "active")
        self.assertIn("گیگ", result.volume)
        self.assertIn("ذخیره‌شده", result.source)
        self.assertIn("پاسخ", result.warning)
        self.assertEqual(result.used, "—")

    async def test_incomplete_panel_response_keeps_local_values(self) -> None:
        self.fetch.return_value = {"status": "disabled", **service_info_error("incomplete_response")}
        result = await self.preview()
        self.assertEqual(result.status, "active")
        self.assertTrue(result.warning)

    async def test_shop_status_filters_exclude_other_shops_services(self) -> None:
        async with self.Session() as session:
            user = await session.get(BotUser, 7)
            rows, counts, key = await build_users_ops_page(
                session, [user], shop_id=5, filter_key="expired", wallet_by_uid={7: 0}
            )
        self.assertEqual(key, "expired")
        self.assertEqual(rows, [])
        self.assertEqual(counts["active"], 1)
        self.assertEqual(counts["expired"], 0)
        self.assertEqual(counts["limited"], 0)

    async def test_endpoint_returns_no_secrets_and_no_store_header(self) -> None:
        app = FastAPI()
        async def staff() -> dict:
            return SHOP
        async def db():
            async with self.Session() as session:
                yield session
        register_user_service_preview_pages(app, require_staff=staff, get_db=db)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/users/7/services/11/preview")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.json()["username"], HOSTILE)
            self.assertNotIn("secret", response.text)
            wrong = await client.get("/users/8/services/11/preview")
            self.assertEqual(wrong.status_code, 404)
            self.assertNotIn(HOSTILE, wrong.text)
