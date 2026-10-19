"""«بزن به کارت» needs an https panel address: customers get a neutral text, owners a clear reason and a guard."""

from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy import func, select

from app.bot.handlers import shop as shop_handlers
from app.db.models import PaymentSettlement
from app.services import bbc_settlement as flow
from app.services.users import clear_settings_cache, set_setting
from tests.test_bezanbecard_settlement import _Db


class HttpsRequirementTests(_Db):
    def http_only(self):
        patcher = patch.object(flow, "_public_base", return_value="http://203.0.113.5:9000")
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_checkout_on_a_plain_http_panel_is_refused_before_any_record_is_created(self) -> None:
        self.http_only()
        async with self.Session() as session:
            payment = await self._payment(session)
            with self.assertRaises(flow.BbcNotReady):
                await flow.start_bbc_checkout(session, payment)
            rows = await session.scalar(select(func.count()).select_from(PaymentSettlement))
        self.assertEqual(rows, 0)

    async def test_gateway_readiness_checks_the_key_and_the_address(self) -> None:
        async with self.Session() as session:
            await flow.ensure_gateway_ready(session, None)
            await set_setting(session, "bbc_api_key", "", reseller_id=5)
            clear_settings_cache()
            with self.assertRaises(flow.BbcNotReady):
                await flow.ensure_gateway_ready(session, 5)
        self.http_only()
        async with self.Session() as session:
            with self.assertRaises(flow.BbcNotReady):
                await flow.ensure_gateway_ready(session, None)

    async def test_the_customer_sees_a_neutral_text_not_the_setup_detail(self) -> None:
        self.http_only()
        callback = MagicMock(data="pay:bbc:1", answer=AsyncMock(), message=MagicMock())
        order = MagicMock(id=1)
        async with self.Session() as session:
            with patch.object(shop_handlers, "is_customer_order_in_current_shop", return_value=True), \
                    patch.object(session, "get", AsyncMock(return_value=order)):
                await shop_handlers.pay_bbc_cb(callback, session, MagicMock(id=1))
        shown = callback.answer.await_args.args[0]
        self.assertEqual(shown, flow.CUSTOMER_UNAVAILABLE)
        self.assertNotIn("https", shown)

    async def test_switching_the_gateway_on_without_https_is_refused_but_an_already_on_gateway_does_not_block_saving(self) -> None:
        self.http_only()
        async with self.Session() as session:
            await set_setting(session, "pay_bbc_enabled", "0", reseller_id=5)
            clear_settings_cache()
            self.assertEqual(await flow.bbc_enable_error(session, {"pay_bbc_enabled": "1"}, reseller_id=5), flow.HTTPS_REQUIRED)
            self.assertIsNone(await flow.bbc_enable_error(session, {"pay_bbc_enabled": "0"}, reseller_id=5))
            # The platform gateway was already on in the fixture, so unrelated saves keep working.
            self.assertIsNone(await flow.bbc_enable_error(session, {"pay_bbc_enabled": "1"}, reseller_id=None))

    async def test_an_https_address_allows_enabling(self) -> None:
        async with self.Session() as session:
            await set_setting(session, "pay_bbc_enabled", "0", reseller_id=5)
            clear_settings_cache()
            self.assertIsNone(await flow.bbc_enable_error(session, {"pay_bbc_enabled": "1"}, reseller_id=5))


class SecretFieldTests(unittest.TestCase):
    def render(self, value: str) -> str:
        from app.api.app import templates

        field = ("bbc_api_key", "کلید API", "password", "")
        return templates.env.from_string(
            '{% set field = field %}{% include "_settings_field.html" %}'
        ).render(field=field, values={"bbc_api_key": value})

    def test_a_saved_secret_is_marked_as_saved_without_showing_it(self) -> None:
        html = self.render("sk-live-123456789")
        self.assertIn("ذخیره شده", html)
        self.assertNotIn("sk-live-123456789", html)

    def test_an_empty_secret_is_not_marked_as_saved(self) -> None:
        self.assertNotIn("ذخیره شده", self.render(""))
