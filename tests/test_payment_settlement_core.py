"""Payment settlement core — mock-first, fail-closed, additive."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


ROOT = Path(__file__).resolve().parents[1]


class CardAutoCryptoTests(unittest.TestCase):
    def test_sign_verify_roundtrip(self):
        from app.services.payment_providers.card_auto import (
            dumps_canonical,
            parse_card_auto_event,
            sign_payload,
            verify_signature,
        )

        payload = {"amount": 150000, "external_ref": "evt-1", "payment_id": 42}
        body = dumps_canonical(payload)
        sig = sign_payload("secret-test", body)
        self.assertTrue(verify_signature(secret="secret-test", body=body, signature=sig))
        self.assertFalse(verify_signature(secret="wrong", body=body, signature=sig))
        ev = parse_card_auto_event(payload)
        self.assertEqual(ev.amount, 150000)
        self.assertEqual(ev.payment_id, 42)
        self.assertEqual(ev.external_ref, "evt-1")

    def test_parse_rejects_bad_amount(self):
        from app.services.payment_providers.card_auto import parse_card_auto_event

        with self.assertRaises(ValueError):
            parse_card_auto_event({"external_ref": "x", "amount": 0})
        with self.assertRaises(ValueError):
            parse_card_auto_event({"amount": 10})


class MockPspAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_checkout_and_verify(self):
        from app.services.payment_providers.base import CheckoutRequest
        from app.services.payment_providers.mock_psp import MockPspAdapter

        adapter = MockPspAdapter(public_base_url="http://127.0.0.1:8000")
        req = CheckoutRequest(
            settlement_id=9,
            payment_id=3,
            amount=50000,
            currency="IRT",
            description="t",
            callback_url="http://127.0.0.1:8000/cb",
            return_url="http://127.0.0.1:8000/cb",
            metadata={},
        )
        result = await adapter.create_checkout(req)
        self.assertIn("settlement_id=9", result.checkout_url)
        self.assertTrue(result.external_ref.startswith("mock-"))
        ok = await adapter.verify(
            external_ref=result.external_ref,
            amount=50000,
            callback_params={"status": "ok", "amount": 50000},
        )
        self.assertTrue(ok.ok)
        bad = await adapter.verify(
            external_ref=result.external_ref,
            amount=50000,
            callback_params={"status": "ok", "amount": 1},
        )
        self.assertFalse(bad.ok)


class ZarinpalFailClosedTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_merchant_refuses_checkout(self):
        from app.services.payment_providers.base import CheckoutRequest
        from app.services.payment_providers.zarinpal import ZarinpalAdapter

        adapter = ZarinpalAdapter(merchant_id="", sandbox=True)
        req = CheckoutRequest(
            settlement_id=1,
            payment_id=1,
            amount=1000,
            currency="IRT",
            description="t",
            callback_url="http://x/cb",
            return_url="http://x/cb",
            metadata={},
        )
        with self.assertRaises(ValueError):
            await adapter.create_checkout(req)


class SettlementWiringTests(unittest.TestCase):
    def test_model_and_migration(self):
        models = (ROOT / "app/db/models.py").read_text(encoding="utf-8")
        self.assertIn('PSP = "psp"', models)
        self.assertIn("class PaymentSettlement", models)
        self.assertIn("class SettlementStatus", models)
        mig = (ROOT / "alembic/versions/0021_payment_settlements.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("payment_settlements", mig)
        self.assertIn('down_revision: Union[str, None] = "0020_inbox_dismissals"', mig)

    def test_settings_keys(self):
        src = (ROOT / "app/services/users.py").read_text(encoding="utf-8")
        for key in (
            "pay_psp_enabled",
            "pay_card_auto_enabled",
            "psp_provider",
            "psp_merchant_id",
            "card_auto_webhook_secret",
            "btn_pay_psp",
            "درگاه آنلاین API",
            "تأیید خودکار کارت",
        ):
            self.assertIn(key, src)

    def test_routes_registered(self):
        pages = (ROOT / "app/api/settlement_pages.py").read_text(encoding="utf-8")
        self.assertIn("/payments/settlement/mock/checkout", pages)
        self.assertIn("/payments/settlement/card-auto/webhook", pages)
        self.assertIn("/payments/settlement/psp/{provider}/return/{settlement_id}", pages)
        app_src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("register_settlement_pages", app_src)

    def test_bot_additive_psp(self):
        kb = (ROOT / "app/bot/keyboards.py").read_text(encoding="utf-8")
        self.assertIn("pay:psp:", kb)
        self.assertIn("pay_psp_enabled", kb)
        self.assertIn("REPLY_ACTION_PAY_PSP", kb)
        shop = (ROOT / "app/bot/handlers/shop.py").read_text(encoding="utf-8")
        self.assertIn("pay_psp_cb", shop)
        self.assertIn("create_psp_checkout", shop)
        self.assertIn("create_card_auto_awaiting", shop)
        # Existing gateway path still present
        self.assertIn("pay_gateway_cb", shop)
        self.assertIn("pay_gateway_enabled", kb)


class SettlementFlowDbTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.db import Base
        from app.db.models import (  # noqa: F401 — register mappers
            BotUser,
            Order,
            Payment,
            PaymentSettlement,
            Plan,
        )

        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "t.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def asyncTearDown(self):
        await self.engine.dispose()
        self._tmp.cleanup()

    async def _seed_pending_payment(self, session, *, amount: int = 100000):
        from app.db.models import BotUser, Order, OrderStatus, Payment, PaymentMethod, PaymentStatus

        user = BotUser(
            telegram_id=900001,
            username="t",
            full_name="t",
            referral_code="SETL900001",
        )
        session.add(user)
        await session.flush()
        order = Order(
            user_id=user.id,
            amount=amount,
            status=OrderStatus.AWAITING_RECEIPT.value,
            payment_method=PaymentMethod.PSP.value,
        )
        session.add(order)
        await session.flush()
        payment = Payment(
            order_id=order.id,
            user_id=user.id,
            amount=amount,
            method=PaymentMethod.PSP.value,
            status=PaymentStatus.PENDING.value,
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        return payment

    async def test_mock_psp_settle_amount_mismatch_fail_closed(self):
        from app.db.models import PaymentSettlement, SettlementStatus
        from app.services.payment_settlement import settle_and_approve
        from app.services.users import set_setting

        async with self.Session() as session:
            payment = await self._seed_pending_payment(session, amount=100000)
            settlement = PaymentSettlement(
                payment_id=payment.id,
                channel="psp",
                provider="mock",
                status=SettlementStatus.AWAITING.value,
                amount=100000,
                currency="IRT",
                idempotency_key=f"t-{payment.id}",
                external_ref="mock-x",
            )
            session.add(settlement)
            await session.commit()
            await session.refresh(settlement)
            with self.assertRaises(ValueError):
                await settle_and_approve(
                    session,
                    settlement,
                    expected_amount=99999,
                    external_ref="mock-x",
                )
            await session.refresh(settlement)
            self.assertEqual(settlement.status, SettlementStatus.FAILED.value)

    async def test_card_auto_signature_and_idempotent_ref(self):
        from app.db.models import (
            BotUser,
            Order,
            OrderStatus,
            Payment,
            PaymentMethod,
            PaymentSettlement,
            PaymentStatus,
            SettlementStatus,
        )
        from app.services.payment_providers.card_auto import dumps_canonical, sign_payload
        from app.services.payment_settlement import handle_card_auto_webhook
        from app.services.users import set_setting

        async with self.Session() as session:
            await set_setting(session, "pay_card_auto_enabled", "1")
            await set_setting(session, "card_auto_webhook_secret", "whsec")
            user = BotUser(
                telegram_id=900002,
                username="c",
                full_name="c",
                referral_code="SETL900002",
            )
            session.add(user)
            await session.flush()
            order = Order(
                user_id=user.id,
                amount=77000,
                status=OrderStatus.AWAITING_RECEIPT.value,
                payment_method=PaymentMethod.CARD.value,
            )
            session.add(order)
            await session.flush()
            payment = Payment(
                order_id=order.id,
                user_id=user.id,
                amount=77000,
                method=PaymentMethod.CARD.value,
                status=PaymentStatus.PENDING.value,
                receipt_file_id="card_auto:awaiting:x",
            )
            session.add(payment)
            await session.flush()
            session.add(
                PaymentSettlement(
                    payment_id=payment.id,
                    channel="card_auto",
                    provider="generic",
                    status=SettlementStatus.AWAITING.value,
                    amount=77000,
                    currency="IRT",
                    idempotency_key=f"ca-{payment.id}",
                )
            )
            await session.commit()
            await session.refresh(payment)

            payload = {
                "amount": 77000,
                "external_ref": "bank-evt-1",
                "payment_id": payment.id,
            }
            body = dumps_canonical(payload)
            sig = sign_payload("whsec", body)

            # Patch approve_payment to avoid full delivery stack in unit test.
            import app.services.payment_settlement as ps

            async def _fake_approve(session, payment, reviewer_tg=0):
                payment.status = PaymentStatus.APPROVED.value
                await session.commit()
                return None

            orig = ps.approve_payment
            ps.approve_payment = _fake_approve
            try:
                s1 = await handle_card_auto_webhook(
                    session, body=body, signature=sig, reseller_id=None
                )
                self.assertEqual(s1.status, SettlementStatus.SETTLED.value)
                s2 = await handle_card_auto_webhook(
                    session, body=body, signature=sig, reseller_id=None
                )
                self.assertEqual(s2.id, s1.id)
            finally:
                ps.approve_payment = orig


if __name__ == "__main__":
    unittest.main()
