"""Payment settlement core — security, tenant isolation, mock-gated."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ["ALLOW_SETTLEMENT_MOCK"] = "1"

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
        sig = sign_payload("secret-test-16chars", body)
        self.assertTrue(
            verify_signature(secret="secret-test-16chars", body=body, signature=sig)
        )
        self.assertFalse(verify_signature(secret="wrong", body=body, signature=sig))
        ev = parse_card_auto_event(payload)
        self.assertEqual(ev.payment_id, 42)

    def test_parse_requires_external_ref(self):
        from app.services.payment_providers.card_auto import parse_card_auto_event

        with self.assertRaises(ValueError):
            parse_card_auto_event({"amount": 10})


class MockGateTests(unittest.TestCase):
    def test_mock_off_by_default_config(self):
        from app.config import Settings

        s = Settings.model_construct(allow_settlement_mock=False)
        self.assertFalse(s.allow_settlement_mock)

    def test_mock_routes_require_env(self):
        pages = (ROOT / "app/api/settlement_pages.py").read_text(encoding="utf-8")
        self.assertIn("settlement_mock_allowed", pages)
        self.assertIn("status_code=404", pages)
        self.assertIn("/card-auto/platform/webhook", pages)
        self.assertIn("/card-auto/shop/{reseller_id}/webhook", pages)
        self.assertIn("status_code=410", pages)


class SettlementWiringTests(unittest.TestCase):
    def test_model_tenant_columns(self):
        models = (ROOT / "app/db/models.py").read_text(encoding="utf-8")
        self.assertIn("shop_owner_id", models)
        self.assertIn("checkout_token", models)
        mig = (ROOT / "alembic/versions/0021_payment_settlements.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("shop_owner_id", mig)
        self.assertIn("checkout_token", mig)

    def test_secrets_masked_in_panel(self):
        field = (ROOT / "app/web/templates/_settings_field.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("kind == 'password'", field)
        self.assertIn('type="password"', field)
        users = (ROOT / "app/services/users.py").read_text(encoding="utf-8")
        self.assertIn('"psp_provider": "zarinpal"', users)
        self.assertIn("SECRET_KEYS", users)
        self.assertIn('"password"', users)

    def test_bot_panel_parity_keys(self):
        admin = (ROOT / "app/bot/handlers/admin_settings.py").read_text(encoding="utf-8")
        self.assertIn('("psp"', admin)
        self.assertIn('("card_auto"', admin)
        kb = (ROOT / "app/bot/keyboards.py").read_text(encoding="utf-8")
        self.assertIn("REPLY_ACTION_TOPUP_PSP", kb)
        self.assertIn("wtop:psp", kb)
        wallet = (ROOT / "app/bot/handlers/wallet.py").read_text(encoding="utf-8")
        self.assertIn('key == "psp"', wallet)


class SettlementFlowDbTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.db import Base
        import app.db.models  # noqa: F401
        from app.config import get_settings

        get_settings.cache_clear()
        os.environ["ALLOW_SETTLEMENT_MOCK"] = "1"
        get_settings.cache_clear()

        self._tmp = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp.name) / "t.db"
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

    async def test_mock_refused_when_env_off(self):
        from app.db.models import (
            Order,
            OrderStatus,
            Payment,
            PaymentMethod,
            PaymentStatus,
        )
        from app.services.payment_settlement import create_psp_checkout
        from app.services.users import set_setting

        async with self.Session() as session:
            await set_setting(session, "pay_psp_enabled", "1")
            await set_setting(session, "psp_provider", "mock")
            u = await self._user(session, 91001, "MCK91001")
            order = Order(
                user_id=u.id,
                amount=10000,
                status=OrderStatus.AWAITING_RECEIPT.value,
                payment_method=PaymentMethod.PSP.value,
            )
            session.add(order)
            await session.flush()
            payment = Payment(
                order_id=order.id,
                user_id=u.id,
                amount=10000,
                method=PaymentMethod.PSP.value,
                status=PaymentStatus.PENDING.value,
            )
            session.add(payment)
            await session.commit()
            await session.refresh(payment)

            with patch(
                "app.services.payment_settlement.settlement_mock_allowed",
                return_value=False,
            ):
                with self.assertRaises(ValueError):
                    await create_psp_checkout(session, payment)

    async def test_mock_pay_requires_token(self):
        from app.db.models import (
            Order,
            OrderStatus,
            Payment,
            PaymentMethod,
            PaymentStatus,
        )
        from app.services.payment_settlement import create_psp_checkout, mock_psp_pay
        from app.services.users import set_setting

        async with self.Session() as session:
            await set_setting(session, "pay_psp_enabled", "1")
            await set_setting(session, "psp_provider", "mock")
            u = await self._user(session, 91002, "MCK91002")
            order = Order(
                user_id=u.id,
                amount=20000,
                status=OrderStatus.AWAITING_RECEIPT.value,
                payment_method=PaymentMethod.PSP.value,
            )
            session.add(order)
            await session.flush()
            payment = Payment(
                order_id=order.id,
                user_id=u.id,
                amount=20000,
                method=PaymentMethod.PSP.value,
                status=PaymentStatus.PENDING.value,
            )
            session.add(payment)
            await session.commit()
            await session.refresh(payment)

            with patch(
                "app.services.payment_settlement.settlement_mock_allowed",
                return_value=True,
            ):
                settlement = await create_psp_checkout(session, payment)
                self.assertTrue(settlement.checkout_token)
                self.assertIn("token=", settlement.checkout_url or "")
                with self.assertRaises(ValueError):
                    await mock_psp_pay(
                        session,
                        settlement_id=settlement.id,
                        amount=20000,
                        token="wrong-token",
                    )

    async def test_card_auto_requires_payment_id_and_tenant_secret(self):
        from app.db.models import (
            Order,
            OrderStatus,
            Payment,
            PaymentMethod,
            PaymentSettlement,
            PaymentStatus,
            Role,
            SettlementStatus,
            BotUser,
        )
        from app.services.payment_providers.card_auto import dumps_canonical, sign_payload
        from app.services.payment_settlement import handle_card_auto_webhook
        from app.services.users import set_setting
        import app.services.payment_settlement as ps

        async with self.Session() as session:
            # Platform secret
            await set_setting(session, "pay_card_auto_enabled", "1")
            await set_setting(
                session, "card_auto_webhook_secret", "platform-secret-ok!"
            )

            reseller = BotUser(
                telegram_id=92000,
                referral_code="RES92000",
                role=Role.RESELLER.value,
            )
            session.add(reseller)
            await session.flush()
            # Shop-only secret (different)
            await set_setting(
                session,
                "pay_card_auto_enabled",
                "1",
                reseller_id=reseller.id,
            )
            await set_setting(
                session,
                "card_auto_webhook_secret",
                "shop-secret-sixteen",
                reseller_id=reseller.id,
            )

            buyer = await self._user(
                session, 91003, "BUY91003", reseller_id=reseller.id
            )
            order = Order(
                user_id=buyer.id,
                amount=33000,
                status=OrderStatus.AWAITING_RECEIPT.value,
                payment_method=PaymentMethod.CARD.value,
                reseller_id=reseller.id,
            )
            session.add(order)
            await session.flush()
            payment = Payment(
                order_id=order.id,
                user_id=buyer.id,
                amount=33000,
                method=PaymentMethod.CARD.value,
                status=PaymentStatus.PENDING.value,
            )
            session.add(payment)
            await session.flush()
            session.add(
                PaymentSettlement(
                    payment_id=payment.id,
                    shop_owner_id=reseller.id,
                    channel="card_auto",
                    provider="generic",
                    status=SettlementStatus.AWAITING.value,
                    amount=33000,
                    currency="IRT",
                    idempotency_key=f"ca-{payment.id}",
                )
            )
            await session.commit()
            await session.refresh(payment)

            payload = {
                "amount": 33000,
                "external_ref": "bank-1",
                "payment_id": payment.id,
            }
            body = dumps_canonical(payload)

            # Platform secret must NOT settle shop payment
            sig_plat = sign_payload("platform-secret-ok!", body)
            with self.assertRaises(ValueError):
                await handle_card_auto_webhook(
                    session,
                    body=body,
                    signature=sig_plat,
                    shop_owner_id=reseller.id,
                )

            # Missing payment_id rejected
            bad = dumps_canonical({"amount": 33000, "external_ref": "bank-2"})
            sig_shop = sign_payload("shop-secret-sixteen", bad)
            with self.assertRaises(ValueError):
                await handle_card_auto_webhook(
                    session,
                    body=bad,
                    signature=sig_shop,
                    shop_owner_id=reseller.id,
                )

            # Correct shop secret + payment_id works (approve stubbed)
            async def _fake_approve(session, payment, reviewer_tg=0):
                payment.status = PaymentStatus.APPROVED.value
                await session.commit()
                return None

            orig = ps.approve_payment
            ps.approve_payment = _fake_approve
            try:
                sig_ok = sign_payload("shop-secret-sixteen", body)
                s = await handle_card_auto_webhook(
                    session,
                    body=body,
                    signature=sig_ok,
                    shop_owner_id=reseller.id,
                )
                self.assertEqual(s.status, SettlementStatus.SETTLED.value)
                self.assertEqual(s.shop_owner_id, reseller.id)
            finally:
                ps.approve_payment = orig

    async def test_amount_mismatch_fail_closed(self):
        from app.db.models import (
            Order,
            OrderStatus,
            Payment,
            PaymentMethod,
            PaymentSettlement,
            PaymentStatus,
            SettlementStatus,
        )
        from app.services.payment_settlement import settle_and_approve

        async with self.Session() as session:
            u = await self._user(session, 91004, "AM91004")
            order = Order(
                user_id=u.id,
                amount=100000,
                status=OrderStatus.AWAITING_RECEIPT.value,
                payment_method=PaymentMethod.PSP.value,
            )
            session.add(order)
            await session.flush()
            payment = Payment(
                order_id=order.id,
                user_id=u.id,
                amount=100000,
                method=PaymentMethod.PSP.value,
                status=PaymentStatus.PENDING.value,
            )
            session.add(payment)
            await session.flush()
            settlement = PaymentSettlement(
                payment_id=payment.id,
                shop_owner_id=None,
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


if __name__ == "__main__":
    unittest.main()
