"""Settlement return pages + Telegram checkout button redirect (panel-hosted)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from jinja2 import Environment, FileSystemLoader, select_autoescape
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
from app.services.payment_settlement import CHANNEL_PSP, public_checkout_button_url
from app.services.users import clear_settings_cache

ROOT = Path(__file__).resolve().parents[1]


class SettlementStatusTemplateTests(unittest.TestCase):
    def render(self, **kwargs) -> str:
        env = Environment(
            loader=FileSystemLoader(str(ROOT / "app" / "web" / "templates")),
            autoescape=select_autoescape(["html", "xml"]),
        )
        base = {
            "code": "ok",
            "title": "پرداخت تأیید شد",
            "message": "می‌توانید به تلگرام برگردید.",
            "watermark": "OK",
            "kicker": "پرداخت",
            "ref": None,
            "primary_href": "",
            "primary_label": "",
            "secondary_href": "",
            "secondary_label": "",
            "guide_heading": "",
            "guide_steps": [],
            "code_block": "",
            "guide_note": "",
            "body_html": "",
            "footer": "این صفحه را ببندید و به تلگرام برگردید.",
            "app_version": "0.0.0",
            "pwa_name": "MrClockBot",
        }
        base.update(kwargs)
        return env.get_template("panel_status.html").render(**base)

    def test_success_tone_uses_ok_status(self) -> None:
        html = self.render()
        self.assertIn('data-status="ok"', html)
        self.assertIn("پرداخت تأیید شد", html)
        self.assertIn("می‌توانید به تلگرام برگردید", html)

    def test_warn_and_error_tones(self) -> None:
        warn = self.render(code="warn", title="در حال بررسی", watermark="WARN")
        err = self.render(code="error", title="ناموفق", watermark="ERR")
        self.assertIn('data-status="warn"', warn)
        self.assertIn('data-status="error"', err)


class PublicCheckoutButtonUrlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        clear_settings_cache()
        self._tmp = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self._tmp.name) / 'ux.db'}"
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self._tmp.cleanup()

    async def test_button_uses_panel_go_link_not_psp_host(self) -> None:
        async with self.Session() as session:
            session.add(BotUser(id=1, telegram_id=101, referral_code="u1", role=Role.USER.value))
            payment = Payment(
                user_id=1,
                amount=50_000,
                method=PaymentMethod.PSP.value,
                status=PaymentStatus.PENDING.value,
                is_wallet_topup=True,
            )
            session.add(payment)
            await session.flush()
            settlement = PaymentSettlement(
                payment_id=payment.id,
                shop_owner_id=None,
                tenant_key=0,
                channel=CHANNEL_PSP,
                provider="sunpay",
                status=SettlementStatus.AWAITING.value,
                amount=50_000,
                currency="IRT",
                idempotency_key="psp:ux:1",
                checkout_token="tok-abc",
                checkout_url="https://payment.example.ir/pay/uuid-here",
            )
            session.add(settlement)
            await session.commit()
            await session.refresh(settlement)

        with patch(
            "app.services.public_https.https_public_base",
            return_value="https://bot.example.com",
        ):
            link = public_checkout_button_url(settlement)
        self.assertTrue(link.startswith("https://bot.example.com/payments/settlement/go/"))
        self.assertIn("t=tok-abc", link)
        self.assertNotIn("payment.example.ir", link)

    def test_falls_back_to_raw_checkout_without_base(self) -> None:
        settlement = MagicMock(
            id=9,
            checkout_token="tok",
            checkout_url="https://payment.example.ir/pay/x",
        )
        with patch(
            "app.services.public_https.https_public_base", return_value=""
        ), patch(
            "app.services.payment_settlement._public_base", return_value=""
        ):
            self.assertEqual(
                public_checkout_button_url(settlement),
                "https://payment.example.ir/pay/x",
            )


if __name__ == "__main__":
    unittest.main()
