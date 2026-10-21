"""SunPay PSP — request/verify contract, amount match, soft cancel, tenant settle."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base
from app.db.models import (
    BotUser,
    Payment,
    PaymentMethod,
    PaymentSettlement,
    PaymentStatus,
    Role,
    SettlementStatus,
)
from app.services.payment_providers import get_psp_adapter
from app.services.payment_providers.base import CheckoutRequest
from app.services.payment_providers.sunpay import SunPayAdapter
from app.services.payment_settlement import (
    callback_indicates_user_abort,
    callback_invoice_matches_settlement,
    complete_psp_return,
    create_psp_checkout,
)
from app.services.users import clear_settings_cache, set_setting

PAY_URL = "https://pay.sunpay.test"
API_KEY = "sunpay-test-key-abcdef"
TOKEN = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _patch_httpx(handler):
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs = dict(kwargs)
        kwargs["transport"] = httpx.MockTransport(handler)
        kwargs.pop("base_url", None)
        return real_async_client(*args, **kwargs)

    return patch.object(httpx, "AsyncClient", side_effect=factory)


def _checkout_req(*, settlement_id: int = 42, amount: int = 100_000) -> CheckoutRequest:
    return CheckoutRequest(
        settlement_id=settlement_id,
        payment_id=7,
        amount=amount,
        currency="IRT",
        description="test",
        callback_url="https://bot.test/payments/settlement/psp/sunpay/return/42",
        return_url="https://bot.test/payments/settlement/psp/sunpay/return/42",
        metadata={},
    )


class SunPayClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_sends_documented_get_json_body(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"success": 1, "data": {"token": TOKEN}})

        with _patch_httpx(handler):
            adapter = SunPayAdapter(api_key=API_KEY, pay_url=PAY_URL)
            result = await adapter.create_checkout(_checkout_req())
        self.assertEqual(result.external_ref, TOKEN)
        self.assertEqual(result.checkout_url, f"{PAY_URL}/pay/{TOKEN}")
        sent = seen[0]
        self.assertEqual(sent.method, "GET")
        self.assertEqual(sent.url.path, "/api/request")
        self.assertIn("application/json", sent.headers.get("content-type", ""))
        body = json.loads(sent.content)
        self.assertEqual(body["api_key"], API_KEY)
        self.assertEqual(body["amount"], 100_000)
        self.assertEqual(body["invoice_id"], 42)
        self.assertTrue(body["callback"].startswith("https://bot.test/"))

    async def test_request_rejects_amount_below_minimum_and_bool(self) -> None:
        adapter = SunPayAdapter(api_key=API_KEY, pay_url=PAY_URL)
        with self.assertRaises(ValueError):
            await adapter.create_checkout(_checkout_req(amount=999))
        with self.assertRaises(ValueError):
            await adapter.create_checkout(_checkout_req(amount=True))  # type: ignore[arg-type]

    async def test_request_fail_closed_without_credentials(self) -> None:
        with self.assertRaises(ValueError):
            await SunPayAdapter(api_key="", pay_url=PAY_URL).create_checkout(
                _checkout_req()
            )
        with self.assertRaises(ValueError):
            await SunPayAdapter(api_key=API_KEY, pay_url="").create_checkout(
                _checkout_req()
            )

    async def test_request_maps_api_error_without_raw_message(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "success": 0,
                    "error": {"code": "BAD_KEY", "message": "<b>secret</b>"},
                },
            )

        with _patch_httpx(handler):
            adapter = SunPayAdapter(api_key=API_KEY, pay_url=PAY_URL)
            with self.assertRaises(ValueError) as caught:
                await adapter.create_checkout(_checkout_req())
        self.assertIn("BAD_KEY", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))

    async def test_verify_posts_token_and_matches_amount(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(
                200,
                json={
                    "success": 1,
                    "data": {
                        "amount": 50_000,
                        "invoice_id": 9,
                        "reference": "REF-1",
                        "paid_at": "2026-09-27 09:30:00",
                        "detail": {},
                    },
                },
            )

        with _patch_httpx(handler):
            adapter = SunPayAdapter(api_key=API_KEY, pay_url=PAY_URL)
            verified = await adapter.verify(
                external_ref=TOKEN,
                amount=50_000,
                callback_params={"success": "1", "invoice_id": "9", "token": TOKEN},
            )
        self.assertTrue(verified.ok)
        self.assertEqual(verified.amount, 50_000)
        self.assertEqual(verified.message, "REF-1")
        sent = seen[0]
        self.assertEqual(sent.method, "POST")
        self.assertEqual(sent.url.path, "/api/verified")
        self.assertEqual(json.loads(sent.content), {"api_key": API_KEY, "token": TOKEN})

    async def test_verify_soft_abort_without_calling_api(self) -> None:
        calls = {"n": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(500, text="nope")

        with _patch_httpx(handler):
            adapter = SunPayAdapter(api_key=API_KEY, pay_url=PAY_URL)
            verified = await adapter.verify(
                external_ref=TOKEN,
                amount=50_000,
                callback_params={"success": "0", "token": TOKEN, "invoice_id": "1"},
            )
        self.assertFalse(verified.ok)
        self.assertEqual(calls["n"], 0)

    async def test_verify_amount_mismatch(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "success": 1,
                    "data": {
                        "amount": 40_000,
                        "invoice_id": 1,
                        "reference": "X",
                        "paid_at": "2026-09-27 09:30:00",
                        "detail": {},
                    },
                },
            )

        with _patch_httpx(handler):
            adapter = SunPayAdapter(api_key=API_KEY, pay_url=PAY_URL)
            verified = await adapter.verify(
                external_ref=TOKEN,
                amount=50_000,
                callback_params={"success": 1, "token": TOKEN},
            )
        self.assertFalse(verified.ok)
        self.assertEqual(verified.amount, 40_000)

    async def test_verify_token_mismatch(self) -> None:
        adapter = SunPayAdapter(api_key=API_KEY, pay_url=PAY_URL)
        verified = await adapter.verify(
            external_ref=TOKEN,
            amount=50_000,
            callback_params={"success": 1, "token": "other-token"},
        )
        self.assertFalse(verified.ok)


class SoftCancelHelperTests(unittest.TestCase):
    def test_zarinpal_nok_and_sunpay_success_zero(self) -> None:
        self.assertTrue(callback_indicates_user_abort({"Status": "NOK"}))
        self.assertTrue(callback_indicates_user_abort({"success": "0"}))
        self.assertTrue(callback_indicates_user_abort({"success": 0}))
        self.assertFalse(callback_indicates_user_abort({"Status": "OK"}))
        self.assertFalse(callback_indicates_user_abort({"success": "1"}))
        self.assertFalse(callback_indicates_user_abort({}))

    def test_invoice_must_match_settlement(self) -> None:
        callback_invoice_matches_settlement({"invoice_id": "15"}, settlement_id=15)
        with self.assertRaises(ValueError):
            callback_invoice_matches_settlement({"invoice_id": "16"}, settlement_id=15)
        with self.assertRaises(ValueError):
            callback_invoice_matches_settlement({"invoice_id": True}, settlement_id=1)


class RegistryTests(unittest.TestCase):
    def test_get_psp_adapter_sunpay(self) -> None:
        adapter = get_psp_adapter(
            "sunpay",
            ui={"psp_merchant_id": API_KEY, "psp_pay_url": PAY_URL},
            public_base_url="https://bot.test",
        )
        self.assertIsInstance(adapter, SunPayAdapter)
        self.assertEqual(adapter.name, "sunpay")


class SunPaySettlementFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from app.config import get_settings

        get_settings.cache_clear()
        clear_settings_cache()
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "t.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def asyncTearDown(self) -> None:
        from app.config import get_settings

        await self.engine.dispose()
        self._tmp.cleanup()
        clear_settings_cache()
        get_settings.cache_clear()

    async def _configure_platform_sunpay(self, session: AsyncSession) -> None:
        await set_setting(session, "pay_psp_enabled", "1")
        await set_setting(session, "psp_provider", "sunpay")
        await set_setting(session, "psp_merchant_id", API_KEY)
        await set_setting(session, "psp_pay_url", PAY_URL)

    async def _seed_wallet_topup(
        self, session: AsyncSession, *, amount: int = 50_000, wallet_shop_id=None
    ) -> Payment:
        user = BotUser(
            telegram_id=1001,
            username="u",
            full_name="u",
            referral_code="r1",
            role=Role.USER.value,
            reseller_id=wallet_shop_id,
        )
        session.add(user)
        await session.flush()
        payment = Payment(
            user_id=user.id,
            amount=amount,
            method=PaymentMethod.PSP.value,
            status=PaymentStatus.PENDING.value,
            is_wallet_topup=True,
            wallet_shop_id=wallet_shop_id,
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        return payment

    def _request_handler(self, *, verify_amount: int = 50_000, verify_invoice: int | None = None):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/api/request"):
                return httpx.Response(
                    200, json={"success": 1, "data": {"token": TOKEN}}
                )
            if request.url.path.endswith("/api/verified"):
                data = {
                    "amount": verify_amount,
                    "reference": "REF-OK",
                    "paid_at": "2026-09-27 09:30:00",
                    "detail": {},
                }
                if verify_invoice is not None:
                    data["invoice_id"] = verify_invoice
                return httpx.Response(200, json={"success": 1, "data": data})
            return httpx.Response(404, text="missing")

        return handler

    async def test_checkout_and_return_settles_once(self) -> None:
        async with self.Session() as session:
            await self._configure_platform_sunpay(session)
            payment = await self._seed_wallet_topup(session)

        approve = AsyncMock(return_value=None)
        with (
            _patch_httpx(self._request_handler()),
            patch(
                "app.services.payment_settlement._public_base",
                return_value="https://bot.test",
            ),
            patch("app.services.payment_settlement.approve_payment", approve),
        ):
            async with self.Session() as session:
                payment = await session.get(Payment, payment.id)
                assert payment is not None
                settlement = await create_psp_checkout(session, payment)
                self.assertEqual(settlement.provider, "sunpay")
                self.assertEqual(settlement.status, SettlementStatus.AWAITING.value)
                self.assertEqual(settlement.external_ref, TOKEN)
                self.assertEqual(settlement.checkout_url, f"{PAY_URL}/pay/{TOKEN}")
                sid = int(settlement.id)

            async with self.Session() as session:
                settled = await complete_psp_return(
                    session,
                    provider="sunpay",
                    settlement_id=sid,
                    callback_params={
                        "success": "1",
                        "invoice_id": str(sid),
                        "token": TOKEN,
                    },
                    reseller_id=None,
                )
                self.assertEqual(settled.status, SettlementStatus.SETTLED.value)
                approve.assert_awaited()

            async with self.Session() as session:
                again = await complete_psp_return(
                    session,
                    provider="sunpay",
                    settlement_id=sid,
                    callback_params={
                        "success": "1",
                        "invoice_id": str(sid),
                        "token": TOKEN,
                    },
                    reseller_id=None,
                )
                self.assertEqual(again.status, SettlementStatus.SETTLED.value)

    async def test_success_zero_does_not_burn_settlement(self) -> None:
        async with self.Session() as session:
            await self._configure_platform_sunpay(session)
            payment = await self._seed_wallet_topup(session)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/api/request"):
                return httpx.Response(
                    200, json={"success": 1, "data": {"token": TOKEN}}
                )
            raise AssertionError("verify must not be called on soft abort")

        with (
            _patch_httpx(handler),
            patch(
                "app.services.payment_settlement._public_base",
                return_value="https://bot.test",
            ),
        ):
            async with self.Session() as session:
                payment = await session.get(Payment, payment.id)
                assert payment is not None
                settlement = await create_psp_checkout(session, payment)
                sid = int(settlement.id)

            async with self.Session() as session:
                with self.assertRaises(ValueError):
                    await complete_psp_return(
                        session,
                        provider="sunpay",
                        settlement_id=sid,
                        callback_params={
                            "success": "0",
                            "invoice_id": str(sid),
                            "token": TOKEN,
                        },
                        reseller_id=None,
                    )
                row = await session.get(PaymentSettlement, sid)
                assert row is not None
                self.assertEqual(row.status, SettlementStatus.AWAITING.value)

    async def test_wrong_shop_cannot_complete_return(self) -> None:
        async with self.Session() as session:
            shop = BotUser(
                telegram_id=2002,
                username="shop",
                full_name="shop",
                referral_code="shop1",
                role=Role.RESELLER.value,
            )
            session.add(shop)
            await session.flush()
            await set_setting(session, "pay_psp_enabled", "1", reseller_id=shop.id)
            await set_setting(session, "psp_provider", "sunpay", reseller_id=shop.id)
            await set_setting(session, "psp_merchant_id", API_KEY, reseller_id=shop.id)
            await set_setting(session, "psp_pay_url", PAY_URL, reseller_id=shop.id)
            payment = await self._seed_wallet_topup(
                session, wallet_shop_id=shop.id
            )
            shop_id = int(shop.id)
            payment_id = int(payment.id)

        with (
            _patch_httpx(self._request_handler()),
            patch(
                "app.services.payment_settlement._public_base",
                return_value="https://bot.test",
            ),
        ):
            async with self.Session() as session:
                payment = await session.get(Payment, payment_id)
                assert payment is not None
                settlement = await create_psp_checkout(
                    session, payment, reseller_id=shop_id
                )
                sid = int(settlement.id)

            async with self.Session() as session:
                with self.assertRaises(ValueError):
                    await complete_psp_return(
                        session,
                        provider="sunpay",
                        settlement_id=sid,
                        callback_params={
                            "success": "1",
                            "invoice_id": str(sid),
                            "token": TOKEN,
                        },
                        reseller_id=999999,
                    )


if __name__ == "__main__":
    unittest.main()
