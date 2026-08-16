"""Mini App security audit — authz, isolation, no leakage."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
PAGES = (ROOT / "app/api/miniapp_pages.py").read_text(encoding="utf-8")
AUTH = (ROOT / "app/services/miniapp_auth.py").read_text(encoding="utf-8")
ORDERS = (ROOT / "app/services/orders.py").read_text(encoding="utf-8")


class MiniAppSecuritySourceTests(unittest.TestCase):
    def test_blocked_users_rejected(self):
        self.assertIn("is_blocked", AUTH)
        self.assertIn("دسترسی شما مسدود شده است", AUTH)

    def test_force_join_gate_for_commerce(self):
        self.assertIn("assert_mini_force_join", AUTH)
        self.assertIn("check_force_join_all", AUTH)
        self.assertIn("_require_commerce_ready", PAGES)
        buy = PAGES.split("async def mini_buy")[1].split("async def mini_renew")[0]
        renew = PAGES.split("async def mini_renew")[1]
        self.assertIn("await _require_commerce_ready", buy)
        self.assertIn("await _require_commerce_ready", renew)

    def test_admin_has_no_commerce_nav_or_payload(self):
        from app.api.miniapp_pages import _nav_for, commerce_allowed

        self.assertFalse(commerce_allowed("admin"))
        self.assertEqual([x["id"] for x in _nav_for("admin")], ["home", "ops"])
        me = PAGES.split("async def mini_me")[1].split("async def mini_service")[0]
        self.assertIn("_empty_customer()", me)

    def test_service_response_has_no_raw_pg_info(self):
        svc = PAGES.split("async def mini_service")[1].split("async def mini_service_qr")[0]
        self.assertNotIn('"info": info', svc)
        self.assertNotIn("'info': info", svc)
        self.assertIn("_serialize_service", svc)

    def test_serialize_allowlist_only(self):
        ser = PAGES.split("def _serialize_service")[1].split("async def _enrich_services")[0]
        for leak in (
            '"subscription_token"',
            "'subscription_token'",
            '"links"',
            '"inbounds"',
            '"proxy_settings"',
            '"note"',
        ):
            self.assertNotIn(leak, ser)

    def test_catalog_platform_only(self):
        self.assertIn("Plan.owner_reseller_id.is_(None)", PAGES)
        buy = PAGES.split("async def mini_buy")[1].split("async def mini_renew")[0]
        self.assertIn("owner_reseller_id is not None", buy)

    def test_ownership_helper_on_service_paths(self):
        self.assertIn("_owned_service_or_404", PAGES)
        for name in ("mini_service", "mini_service_qr", "mini_renew"):
            chunk = PAGES.split(f"async def {name}")[1].split("async def ")[0]
            self.assertIn("_owned_service_or_404", chunk)

    def test_pay_with_wallet_asserts_order_owner(self):
        fn = ORDERS.split("async def pay_with_wallet")[1].split("async def mark_order_free_paid")[0]
        self.assertIn("سفارش متعلق به این کاربر نیست", fn)
        self.assertIn("order.user_id", fn)

    def test_buy_renew_no_exception_text_leak(self):
        buy = PAGES.split("async def mini_buy")[1].split("async def mini_renew")[0]
        renew = PAGES.split("async def mini_renew")[1]
        self.assertIn('raise HTTPException(500, "خرید ناموفق")', buy)
        self.assertIn('raise HTTPException(500, "تمدید ناموفق")', renew)
        # 500 path must not echo exception text
        self.assertNotIn("HTTPException(500, str(exc)", buy)
        self.assertNotIn("HTTPException(500, str(exc)", renew)

    def test_initdata_header_only(self):
        self.assertIn("X-Telegram-Init-Data", AUTH)
        self.assertNotIn("query_params.get", AUTH)
        self.assertIn("hmac.compare_digest", AUTH)

    def test_subscription_info_auth_false(self):
        self.assertIn("auth=False", PAGES)
        self.assertIn("subscription_info", PAGES)

    def test_reseller_ops_fail_closed_on_foreign_profile(self):
        fn = PAGES.split("async def _reseller_ops_payload")[1].split("def register_miniapp_pages")[0]
        self.assertIn("profile.user_id", fn)
        self.assertIn("user.id", fn)


class MiniAppOwnedServiceUnitTests(unittest.TestCase):
    def test_owned_service_rejects_foreign(self):
        from fastapi import HTTPException

        from app.api.miniapp_pages import _owned_service_or_404

        user = SimpleNamespace(id=1)
        foreign = SimpleNamespace(bot_user_id=2, id=9)
        with self.assertRaises(HTTPException) as ctx:
            _owned_service_or_404(foreign, user)
        self.assertEqual(ctx.exception.status_code, 404)
        own = SimpleNamespace(bot_user_id=1, id=3)
        self.assertIs(_owned_service_or_404(own, user), own)

    def test_commerce_matrix(self):
        from app.api.miniapp_pages import _require_commerce, commerce_allowed
        from fastapi import HTTPException

        self.assertTrue(commerce_allowed("user"))
        self.assertTrue(commerce_allowed("reseller"))
        self.assertFalse(commerce_allowed("admin"))
        with self.assertRaises(HTTPException) as ctx:
            _require_commerce(SimpleNamespace(role="admin", telegram_id=1))
        self.assertEqual(ctx.exception.status_code, 403)


class MiniAppBlockedUserUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_blocked_user_raises_403(self):
        from fastapi import HTTPException
        from starlette.requests import Request

        from app.services.miniapp_auth import load_mini_user

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/mini/me",
            "raw_path": b"/api/mini/me",
            "query_string": b"",
            "headers": [(b"x-telegram-init-data", b"dummy")],
            "client": ("127.0.0.1", 123),
            "server": ("test", 443),
        }
        request = Request(scope)
        blocked = SimpleNamespace(id=1, telegram_id=42, is_blocked=True, role="user")
        session = AsyncMock()
        # session.execute(...).scalar_one_or_none()
        result = SimpleNamespace(scalar_one_or_none=lambda: blocked)
        session.execute = AsyncMock(return_value=result)

        with patch(
            "app.services.miniapp_auth.validate_webapp_init_data",
            return_value={"id": 42},
        ), patch(
            "app.services.miniapp_auth.init_data_from_request",
            return_value="dummy",
        ):
            with self.assertRaises(HTTPException) as ctx:
                await load_mini_user(session, request)
        self.assertEqual(ctx.exception.status_code, 403)


class MiniAppPayWalletOwnerUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_foreign_order(self):
        from app.services.orders import pay_with_wallet

        order = SimpleNamespace(
            id=1,
            user_id=10,
            status="pending",
            amount=1000,
            note=None,
            service_id=None,
            plan_id=None,
        )
        user = SimpleNamespace(id=99, wallet_balance=5000)
        session = AsyncMock()
        with self.assertRaises(ValueError) as ctx:
            await pay_with_wallet(session, order, user)
        self.assertIn("متعلق", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
