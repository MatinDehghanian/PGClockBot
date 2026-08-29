"""Public settlement endpoints — PSP return, mock checkout, card-auto webhook.

No panel session required. Fail-closed; additive to receipt-based methods.
"""

from __future__ import annotations

import logging
from html import escape

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Order, Payment, SettlementStatus

logger = logging.getLogger(__name__)


def _html_page(title: str, body: str, *, ok: bool = True) -> HTMLResponse:
    color = "#16a34a" if ok else "#dc2626"
    doc = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{escape(title)}</title>
<style>
body{{font-family:Tahoma,Arial,sans-serif;background:#f4f4f5;margin:0;padding:24px;color:#18181b}}
.card{{max-width:420px;margin:40px auto;background:#fff;border-radius:12px;padding:24px;
box-shadow:0 1px 3px rgba(0,0,0,.08);text-align:center}}
h1{{font-size:1.15rem;margin:0 0 12px;color:{color}}}
p{{margin:8px 0;line-height:1.7;font-size:.95rem}}
.btn{{display:inline-block;margin-top:16px;padding:10px 20px;background:#2563eb;color:#fff;
text-decoration:none;border:0;border-radius:8px;font:inherit;cursor:pointer}}
.muted{{color:#71717a;font-size:.85rem}}
</style>
</head>
<body><div class="card">{body}</div></body></html>"""
    return HTMLResponse(doc)


def register_settlement_pages(app, *, get_db):
    @app.get("/payments/settlement/mock/checkout", response_class=HTMLResponse)
    async def mock_checkout_page(
        request: Request,
        session: AsyncSession = Depends(get_db),
    ):
        from app.db.models import PaymentSettlement
        from app.services.payment_settlement import CHANNEL_PSP

        sid = request.query_params.get("settlement_id") or ""
        try:
            settlement_id = int(sid)
        except (TypeError, ValueError):
            return _html_page("خطا", "<h1>شناسه نامعتبر</h1>", ok=False)
        settlement = await session.get(PaymentSettlement, settlement_id)
        if (
            not settlement
            or settlement.channel != CHANNEL_PSP
            or settlement.provider != "mock"
        ):
            return _html_page("خطا", "<h1>تسویه mock یافت نشد</h1>", ok=False)
        if settlement.status == SettlementStatus.SETTLED.value:
            return _html_page(
                "پرداخت شده",
                f"<h1>قبلاً تسویه شده</h1><p class='muted'>#{settlement.id}</p>",
            )
        amount = int(settlement.amount)
        body = f"""
<h1>درگاه آزمایشی (Mock)</h1>
<p>مبلغ: <b>{amount:,}</b> تومان</p>
<p class="muted">پرداخت #{settlement.payment_id} · تسویه #{settlement.id}</p>
<form method="post" action="/payments/settlement/mock/pay">
  <input type="hidden" name="settlement_id" value="{settlement.id}"/>
  <input type="hidden" name="amount" value="{amount}"/>
  <button class="btn" type="submit">پرداخت آزمایشی موفق</button>
</form>
<p class="muted">بدون مرچنت واقعی — فقط برای تست محلی</p>
"""
        return _html_page("Mock PSP", body)

    @app.post("/payments/settlement/mock/pay", response_class=HTMLResponse)
    async def mock_pay(
        settlement_id: int = Form(...),
        amount: int = Form(...),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.payment_settlement import mock_psp_pay, notify_after_settlement

        try:
            settlement = await mock_psp_pay(
                session, settlement_id=settlement_id, amount=amount
            )
        except ValueError as exc:
            return _html_page("ناموفق", f"<h1>خطا</h1><p>{escape(str(exc))}</p>", ok=False)
        payment = await session.get(Payment, int(settlement.payment_id))
        order = None
        if payment and payment.order_id:
            order = await session.get(Order, payment.order_id)
        if payment:
            try:
                await notify_after_settlement(session, payment, order)
            except Exception:
                logger.exception("mock pay notify failed payment=%s", payment.id)
        return _html_page(
            "موفق",
            "<h1>پرداخت آزمایشی تأیید شد</h1>"
            "<p>به ربات برگردید — سرویس در صورت موفقیت تحویل می‌شود.</p>",
        )

    @app.get("/payments/settlement/psp/{provider}/return/{settlement_id}")
    async def psp_return(
        provider: str,
        settlement_id: int,
        request: Request,
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.payment_settlement import complete_psp_return, notify_after_settlement

        params = dict(request.query_params)
        # Resolve shop settings from payment/order when possible.
        reseller_id = None
        from app.db.models import PaymentSettlement

        pre = await session.get(PaymentSettlement, settlement_id)
        if pre:
            pay = await session.get(Payment, int(pre.payment_id))
            if pay and pay.order_id:
                ord_row = await session.get(Order, pay.order_id)
                if ord_row and ord_row.reseller_id:
                    reseller_id = int(ord_row.reseller_id)

        try:
            settlement = await complete_psp_return(
                session,
                provider=provider,
                settlement_id=settlement_id,
                callback_params=params,
                reseller_id=reseller_id,
            )
        except ValueError as exc:
            return _html_page(
                "ناموفق",
                f"<h1>تأیید پرداخت ناموفق</h1><p>{escape(str(exc))}</p>"
                "<p class='muted'>اگر مبلغ کم شده با پشتیبانی تماس بگیرید.</p>",
                ok=False,
            )
        payment = await session.get(Payment, int(settlement.payment_id))
        order = None
        if payment and payment.order_id:
            order = await session.get(Order, payment.order_id)
        if payment and settlement.status == SettlementStatus.SETTLED.value:
            try:
                await notify_after_settlement(session, payment, order)
            except Exception:
                logger.exception("psp return notify failed payment=%s", payment.id)
        return _html_page(
            "موفق",
            "<h1>پرداخت تأیید شد</h1>"
            "<p>می‌توانید به تلگرام برگردید.</p>",
        )

    @app.post("/payments/settlement/card-auto/webhook")
    async def card_auto_webhook(
        request: Request,
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.payment_settlement import (
            handle_card_auto_webhook,
            notify_after_settlement,
        )

        body = await request.body()
        signature = (
            request.headers.get("x-signature")
            or request.headers.get("x-card-auto-signature")
            or request.headers.get("x-hub-signature-256")
            or ""
        )
        if signature.lower().startswith("sha256="):
            signature = signature.split("=", 1)[1]
        try:
            settlement = await handle_card_auto_webhook(
                session,
                body=body,
                signature=signature,
                reseller_id=None,
            )
        except ValueError as exc:
            logger.info("card-auto webhook rejected: %s", exc)
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        payment = await session.get(Payment, int(settlement.payment_id))
        order = None
        if payment and payment.order_id:
            order = await session.get(Order, payment.order_id)
        if payment and settlement.status == SettlementStatus.SETTLED.value:
            try:
                await notify_after_settlement(session, payment, order)
            except Exception:
                logger.exception(
                    "card-auto notify failed payment=%s", getattr(payment, "id", None)
                )
        return JSONResponse(
            {
                "ok": True,
                "settlement_id": int(settlement.id),
                "payment_id": int(settlement.payment_id),
                "status": settlement.status,
            }
        )

    @app.get("/payments/settlement/card-auto/webhook")
    async def card_auto_webhook_hint():
        return JSONResponse(
            {
                "ok": True,
                "hint": "POST signed JSON {external_ref, amount, payment_id?} with X-Signature HMAC-SHA256",
            }
        )
