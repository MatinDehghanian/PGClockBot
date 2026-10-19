"""Manual decrease of a PAYG reseller wallet: never below zero, once per form, PAYG only."""

from __future__ import annotations

import os
import unittest
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.reseller_pages import register_reseller_pages
from app.db import Base
from app.db.models import BotUser, ResellerBillingTransaction, ResellerProfile
from app.services.billing import KIND_ADJUSTMENT, debit_adjustment

PAYG_SHOP = 5
FIXED_SHOP = 6


class _Db:
    async def setup(self) -> None:
        self.engine = create_async_engine(
            "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.Session() as session:
            session.add_all([
                BotUser(id=PAYG_SHOP, telegram_id=105, referral_code="p", role="reseller", wallet_balance=50_000),
                BotUser(id=FIXED_SHOP, telegram_id=106, referral_code="f", role="reseller", wallet_balance=50_000),
            ])
            await session.flush()
            session.add_all([
                ResellerProfile(user_id=PAYG_SHOP, billing_mode="payg", payg_wallet_linked=True, billing_balance=50_000),
                ResellerProfile(user_id=FIXED_SHOP, billing_mode="fixed"),
            ])
            await session.commit()

    async def balance(self, user_id: int) -> int:
        async with self.Session() as session:
            return int((await session.get(BotUser, user_id)).wallet_balance)

    async def ledger(self) -> list[ResellerBillingTransaction]:
        async with self.Session() as session:
            return list((await session.execute(select(ResellerBillingTransaction))).scalars())


class DebitAdjustmentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = _Db()
        await self.db.setup()

    async def asyncTearDown(self) -> None:
        await self.db.engine.dispose()

    async def debit(self, amount, key: str = "k1", shop: int = PAYG_SHOP):
        async with self.db.Session() as session:
            return await debit_adjustment(session, shop, amount, created_by="owner", idempotency_key=key)

    async def test_decrease_lowers_the_wallet_and_records_a_negative_entry(self) -> None:
        tx = await self.debit(20_000)
        self.assertEqual(await self.db.balance(PAYG_SHOP), 30_000)
        self.assertEqual((tx.kind, tx.amount, tx.balance_after), (KIND_ADJUSTMENT, -20_000, 30_000))
        async with self.db.Session() as session:
            profile = (await session.execute(select(ResellerProfile).where(ResellerProfile.user_id == PAYG_SHOP))).scalar_one()
        self.assertEqual(profile.billing_balance, 30_000)

    async def test_decrease_above_the_balance_is_refused_and_changes_nothing(self) -> None:
        with self.assertRaises(ValueError):
            await self.debit(60_000)
        self.assertEqual(await self.db.balance(PAYG_SHOP), 50_000)
        self.assertEqual(await self.db.ledger(), [])

    async def test_the_same_form_submitted_twice_decreases_once(self) -> None:
        await self.debit(10_000, key="same")
        await self.debit(10_000, key="same")
        self.assertEqual(await self.db.balance(PAYG_SHOP), 40_000)
        self.assertEqual(len(await self.db.ledger()), 1)

    async def test_a_fixed_plan_reseller_wallet_is_not_touched(self) -> None:
        with self.assertRaises(ValueError):
            await self.debit(10_000, shop=FIXED_SHOP)
        self.assertEqual(await self.db.balance(FIXED_SHOP), 50_000)

    async def test_non_positive_or_non_integer_amounts_are_refused(self) -> None:
        for amount in (0, -1000, True, 1000.0):
            with self.assertRaises(ValueError):
                await self.debit(amount)
        self.assertEqual(await self.db.balance(PAYG_SHOP), 50_000)


class WalletFormTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = _Db()
        await self.db.setup()

        async def get_db():
            async with self.db.Session() as session:
                yield session

        app = FastAPI()
        register_reseller_pages(app, render=None, require_admin=lambda: {"username": "owner"}, get_db=get_db)
        self.client = TestClient(app)

    async def asyncTearDown(self) -> None:
        await self.db.engine.dispose()

    def submit(self, **form) -> dict[str, list[str]]:
        response = self.client.post(f"/resellers/{PAYG_SHOP}/billing-topup", data=form, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        return parse_qs(urlparse(response.headers["location"]).query)

    async def test_the_decrease_button_lowers_the_wallet(self) -> None:
        query = self.submit(amount="15000", mode="debit", nonce="n" * 16)
        self.assertIn("ok", query)
        self.assertEqual(await self.db.balance(PAYG_SHOP), 35_000)

    async def test_a_form_without_a_mode_is_still_a_charge(self) -> None:
        self.submit(amount="15000", nonce="n" * 16)
        self.assertEqual(await self.db.balance(PAYG_SHOP), 65_000)

    async def test_a_decrease_too_large_shows_an_error(self) -> None:
        query = self.submit(amount="90000", mode="debit", nonce="n" * 16)
        self.assertIn("کافی نیست", query["err"][0])
        self.assertEqual(await self.db.balance(PAYG_SHOP), 50_000)

    async def test_a_signed_or_tiny_amount_is_refused(self) -> None:
        for amount in ("-5000", "500"):
            self.assertIn("err", self.submit(amount=amount, mode="debit", nonce="n" * 16))
        self.assertEqual(await self.db.balance(PAYG_SHOP), 50_000)


if __name__ == "__main__":
    unittest.main()
