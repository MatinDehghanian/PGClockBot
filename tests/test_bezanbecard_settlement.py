"""BezanBeCard settlement — tenant isolation, API re-verify, no blind callback trust."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

ROOT = Path(__file__).resolve().parents[1]


class BbcClientUnitTests(unittest.TestCase):
    def test_toman_to_rial_and_rejects_bool(self):
        from app.services.payment_providers.bezanbecard import toman_to_rial

        self.assertEqual(toman_to_rial(20_000), 200_000)
        with self.assertRaises(ValueError):
            toman_to_rial(True)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            toman_to_rial(0)
        with self.assertRaises(ValueError):
            toman_to_rial(500)  # below min rial after ×10

    def test_format_unique_rial_keeps_suffix(self):
        from app.services.payment_providers.bezanbecard import format_unique_rial

        text = format_unique_rial(2_000_043)
        self.assertIn("ریال", text)
        self.assertTrue("2000043" in text.replace(",", "").replace("٬", "") or "۲۰۰۰۰۴۳" in text)

    def test_wiring_settings_and_routes(self):
        from app.services.payment_providers.bezanbecard import SETUP_HELP_FA, SETUP_HELP_HTML

        self.assertIn("https://bezanbecard.ir", SETUP_HELP_FA)
        self.assertIn("طرح دارای API", SETUP_HELP_FA)
        self.assertIn("اعلان تلگرام", SETUP_HELP_FA)
        self.assertIn("bezanbecard.ir", SETUP_HELP_HTML)
        users = (ROOT / "app/services/users.py").read_text(encoding="utf-8")
        self.assertIn('"pay_bbc_enabled"', users)
        self.assertIn('"bbc_api_key"', users)
        self.assertIn("بزن به کارت", users)
        self.assertIn("https://bezanbecard.ir", users)
        admin = (ROOT / "app/bot/handlers/admin_settings.py").read_text(encoding="utf-8")
        self.assertIn("_bbc_fields_intro", admin)
        self.assertIn('sub_id == "bbc"', admin)
        reseller = (ROOT / "app/bot/handlers/reseller_settings.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("SETUP_HELP_HTML", reseller)
        pages = (ROOT / "app/api/settlement_pages.py").read_text(encoding="utf-8")
        self.assertIn("/payments/settlement/bbc/tenant/{tenant_key}/callback/", pages)
        self.assertIn("/payments/settlement/bbc/tenant/{tenant_key}/return/", pages)
        sched = (ROOT / "app/jobs/scheduler.py").read_text(encoding="utf-8")
        self.assertIn("bbc_settlement_poll", sched)
        self.assertIn("run_bbc_settlement_poll", sched)


class BbcSettlementFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import get_settings
        from app.db import Base
        import app.db.models  # noqa: F401

        get_settings.cache_clear()
        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "bbc.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def asyncTearDown(self):
        from app.config import get_settings

        await self.engine.dispose()
        self._tmp.cleanup()
        get_settings.cache_clear()

    async def _user(self, session, tid: int, code: str, *, reseller_id=None):
        from app.db.models import BotUser, Role

        u = BotUser(
            telegram_id=tid,
            username="u",
            full_name="u",
            referral_code=code,
            role=Role.USER.value,
            reseller_id=reseller_id,
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        return u

    async def _set(self, session, key: str, value: str, *, reseller_id=None):
        from app.services.users import set_setting

        await set_setting(session, key, value, reseller_id=reseller_id)

    async def _pending_payment(self, session, user, *, amount: int = 50_000, shop=None):
        from app.db.models import Payment, PaymentMethod, PaymentStatus

        p = Payment(
            user_id=int(user.id),
            amount=amount,
            method=PaymentMethod.BBC.value,
            status=PaymentStatus.PENDING.value,
            is_wallet_topup=True,
            wallet_shop_id=shop,
        )
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return p

    def _create_result(self, *, payment_id: int, unique: int = 500_043):
        from app.services.payment_providers.bezanbecard import BbcCreateResult

        return BbcCreateResult(
            order_id="ord_1",
            payment_token="tok_abc",
            payment_url="https://bezanbecard.ir/pay/tok_abc",
            unique_amount_rial=unique,
            base_amount_rial=500_000,
            status="pending",
            raw={"payment_token": "tok_abc"},
        )

    def _status(self, *, status: str, payment_id: int, unique: int = 500_043):
        from app.services.payment_providers.bezanbecard import BbcOrderStatus

        return BbcOrderStatus(
            order_id="ord_1",
            payment_token="tok_abc",
            status=status,
            unique_amount_rial=unique,
            base_amount_rial=500_000,
            merchant_order_id=str(payment_id),
            raw={"status": status},
        )

    async def test_create_checkout_persists_unique_amount_and_url(self):
        from app.services.payment_settlement import CHANNEL_BBC, create_bbc_checkout

        async with self.Session() as session:
            user = await self._user(session, 101, "c101")
            await self._set(session, "pay_bbc_enabled", "1")
            await self._set(session, "bbc_api_key", "test-api-key-xxxxxx")
            payment = await self._pending_payment(session, user)
            with (
                patch(
                    "app.services.payment_settlement._public_base",
                    return_value="https://bot.example",
                ),
                patch(
                    "app.services.payment_providers.bezanbecard.create_order",
                    new=AsyncMock(return_value=self._create_result(payment_id=payment.id)),
                ),
            ):
                settlement = await create_bbc_checkout(session, payment)

            self.assertEqual(settlement.channel, CHANNEL_BBC)
            self.assertEqual(settlement.external_ref, "tok_abc")
            self.assertTrue(settlement.checkout_url.startswith("https://"))
            self.assertTrue(bool(settlement.checkout_token))
            payload = json.loads(settlement.provider_payload or "{}")
            self.assertEqual(payload["unique_amount_rial"], 500_043)
            self.assertEqual(payload["payment_token"], "tok_abc")

    async def test_callback_without_valid_token_fails_closed(self):
        from app.services.payment_settlement import (
            create_bbc_checkout,
            handle_bbc_callback,
            tenant_key_for,
        )

        async with self.Session() as session:
            user = await self._user(session, 102, "c102")
            await self._set(session, "pay_bbc_enabled", "1")
            await self._set(session, "bbc_api_key", "test-api-key-xxxxxx")
            payment = await self._pending_payment(session, user)
            with (
                patch(
                    "app.services.payment_settlement._public_base",
                    return_value="https://bot.example",
                ),
                patch(
                    "app.services.payment_providers.bezanbecard.create_order",
                    new=AsyncMock(return_value=self._create_result(payment_id=payment.id)),
                ),
            ):
                settlement = await create_bbc_checkout(session, payment)

            with self.assertRaises(ValueError):
                await handle_bbc_callback(
                    session,
                    settlement_id=int(settlement.id),
                    tenant_key=tenant_key_for(None),
                    token="wrong-token",
                )

    async def test_paid_status_settles_and_approves_wallet(self):
        from app.db.models import PaymentStatus, SettlementStatus
        from app.services.payment_settlement import create_bbc_checkout, verify_and_settle_bbc
        from app.services.wallet import get_wallet_balance

        async with self.Session() as session:
            user = await self._user(session, 103, "c103")
            await self._set(session, "pay_bbc_enabled", "1")
            await self._set(session, "bbc_api_key", "test-api-key-xxxxxx")
            payment = await self._pending_payment(session, user, amount=50_000)
            with (
                patch(
                    "app.services.payment_settlement._public_base",
                    return_value="https://bot.example",
                ),
                patch(
                    "app.services.payment_providers.bezanbecard.create_order",
                    new=AsyncMock(return_value=self._create_result(payment_id=payment.id)),
                ),
            ):
                settlement = await create_bbc_checkout(session, payment)

            with patch(
                "app.services.payment_providers.bezanbecard.get_order",
                new=AsyncMock(
                    return_value=self._status(status="paid", payment_id=payment.id)
                ),
            ):
                updated = await verify_and_settle_bbc(
                    session,
                    settlement,
                    checkout_token=settlement.checkout_token,
                    require_token=True,
                )

            self.assertEqual(updated.status, SettlementStatus.SETTLED.value)
            await session.refresh(payment)
            self.assertEqual(payment.status, PaymentStatus.APPROVED.value)
            bal = await get_wallet_balance(session, int(user.id), shop_id=None)
            self.assertEqual(int(bal), 50_000)

    async def test_pending_does_not_approve(self):
        from app.db.models import PaymentStatus, SettlementStatus
        from app.services.payment_settlement import create_bbc_checkout, verify_and_settle_bbc

        async with self.Session() as session:
            user = await self._user(session, 104, "c104")
            await self._set(session, "pay_bbc_enabled", "1")
            await self._set(session, "bbc_api_key", "test-api-key-xxxxxx")
            payment = await self._pending_payment(session, user)
            with (
                patch(
                    "app.services.payment_settlement._public_base",
                    return_value="https://bot.example",
                ),
                patch(
                    "app.services.payment_providers.bezanbecard.create_order",
                    new=AsyncMock(return_value=self._create_result(payment_id=payment.id)),
                ),
            ):
                settlement = await create_bbc_checkout(session, payment)

            with patch(
                "app.services.payment_providers.bezanbecard.get_order",
                new=AsyncMock(
                    return_value=self._status(status="pending", payment_id=payment.id)
                ),
            ):
                updated = await verify_and_settle_bbc(session, settlement)

            self.assertEqual(updated.status, SettlementStatus.AWAITING.value)
            await session.refresh(payment)
            self.assertEqual(payment.status, PaymentStatus.PENDING.value)

    async def test_merchant_order_mismatch_fails(self):
        from app.db.models import SettlementStatus
        from app.services.payment_providers.bezanbecard import BbcOrderStatus
        from app.services.payment_settlement import create_bbc_checkout, verify_and_settle_bbc

        async with self.Session() as session:
            user = await self._user(session, 105, "c105")
            await self._set(session, "pay_bbc_enabled", "1")
            await self._set(session, "bbc_api_key", "test-api-key-xxxxxx")
            payment = await self._pending_payment(session, user)
            with (
                patch(
                    "app.services.payment_settlement._public_base",
                    return_value="https://bot.example",
                ),
                patch(
                    "app.services.payment_providers.bezanbecard.create_order",
                    new=AsyncMock(return_value=self._create_result(payment_id=payment.id)),
                ),
            ):
                settlement = await create_bbc_checkout(session, payment)

            bad = BbcOrderStatus(
                order_id="ord_1",
                payment_token="tok_abc",
                status="paid",
                unique_amount_rial=500_043,
                base_amount_rial=500_000,
                merchant_order_id="999999",
                raw={},
            )
            with patch(
                "app.services.payment_providers.bezanbecard.get_order",
                new=AsyncMock(return_value=bad),
            ):
                with self.assertRaises(ValueError):
                    await verify_and_settle_bbc(session, settlement)
            await session.refresh(settlement)
            self.assertEqual(settlement.status, SettlementStatus.FAILED.value)

    async def test_wrong_shop_api_key_scope_via_tenant_path(self):
        from app.db.models import BotUser, Role
        from app.services.payment_settlement import (
            create_bbc_checkout,
            handle_bbc_callback,
            tenant_key_for,
        )

        async with self.Session() as session:
            owner = BotUser(
                telegram_id=9001,
                username="shop",
                full_name="shop",
                referral_code="shop1",
                role=Role.RESELLER.value,
            )
            session.add(owner)
            await session.commit()
            await session.refresh(owner)

            user = await self._user(session, 106, "c106", reseller_id=owner.id)
            await self._set(session, "pay_bbc_enabled", "1", reseller_id=owner.id)
            await self._set(
                session, "bbc_api_key", "shop-api-key-xxxxxx", reseller_id=owner.id
            )
            payment = await self._pending_payment(
                session, user, shop=int(owner.id)
            )
            with (
                patch(
                    "app.services.payment_settlement._public_base",
                    return_value="https://bot.example",
                ),
                patch(
                    "app.services.payment_providers.bezanbecard.create_order",
                    new=AsyncMock(return_value=self._create_result(payment_id=payment.id)),
                ),
            ):
                settlement = await create_bbc_checkout(session, payment)

            # Platform tenant key must not open a shop settlement.
            with self.assertRaises(ValueError):
                await handle_bbc_callback(
                    session,
                    settlement_id=int(settlement.id),
                    tenant_key=tenant_key_for(None),
                    token=str(settlement.checkout_token),
                )

            with patch(
                "app.services.payment_providers.bezanbecard.get_order",
                new=AsyncMock(
                    return_value=self._status(status="paid", payment_id=payment.id)
                ),
            ):
                ok = await handle_bbc_callback(
                    session,
                    settlement_id=int(settlement.id),
                    tenant_key=tenant_key_for(owner.id),
                    token=str(settlement.checkout_token),
                )
            self.assertEqual(ok.status, "settled")


if __name__ == "__main__":
    unittest.main()
