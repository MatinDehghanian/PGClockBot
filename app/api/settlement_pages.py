"""Settlement HTTP endpoints — fail-closed, tenant-scoped, mock gated.

Public surface:
  - Real PSP return (provider != mock) — verifies via provider API
  - Card-auto webhooks — per-tenant path + HMAC secret from that tenant only
  - BezanBeCard callback/return — tenant path + checkout token; always re-fetches API
  - Mock checkout/pay — ONLY when ALLOW_SETTLEMENT_MOCK=1 + one-time token
"""

from __future__ import annotations

import logging
from html import escape
from typing import Any, Callable

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.status_render import render_status_page
from app.db.models import SettlementStatus

logger = logging.getLogger(__name__)

_TELEGRAM_FOOTER = (
    "اگر این صفحه باز نشد هم اشکالی ندارد؛ نتیجه در ربات می‌آید."
)
_BOT_RETURN_LABEL = "بازگشت به ربات"


async def _bot_return_links(
    session: AsyncSession | None,
    shop_owner_id: int | None,
) -> tuple[str, str]:
    """Return ``(primary_href, https_fallback)`` for the bot CTA.

    Primary prefers ``tg://resolve?domain=…`` so Telegram's in-app browser
    actually opens the chat; HTTPS ``t.me`` is kept as a click fallback.
    """
    from app.services.ux20 import (
        bot_deep_link,
        bot_tg_resolve_link,
        shop_bot_chat_url,
        shop_bot_https_url,
    )

    if session is not None:
        primary = (await shop_bot_chat_url(session, shop_owner_id=shop_owner_id)) or ""
        https = (await shop_bot_https_url(session, shop_owner_id=shop_owner_id)) or ""
        return primary, https

    from app.config import get_settings

    uname = get_settings().bot_username
    primary = bot_tg_resolve_link(uname) or bot_deep_link(uname, "") or ""
    https = bot_deep_link(uname, "") or ""
    return primary, https


async def _status(
    request: Request,
    session: AsyncSession | None = None,
    *,
    shop_owner_id: int | None = None,
    kind: str,
    title: str,
    message: str,
    http_status: int = 200,
    watermark: str | None = None,
    body_html: str = "",
):
    bot_href, bot_https = await _bot_return_links(session, shop_owner_id)
    return render_status_page(
        request,
        kind=kind,
        title=title,
        message=message,
        http_status=http_status,
        watermark=watermark or kind.upper(),
        # No Persian kicker — ``dir=ltr`` + uppercase made «پرداخت» look left-clipped.
        kicker="",
        primary_href=bot_href,
        primary_label=_BOT_RETURN_LABEL if bot_href else "",
        primary_fallback_href=bot_https if bot_https and bot_https != bot_href else "",
        secondary_href="",
        body_html=body_html,
        footer=_TELEGRAM_FOOTER,
        show_close_button=False,
    )


def _sig_from_headers(request: Request) -> str:
    signature = (
        request.headers.get("x-signature")
        or request.headers.get("x-card-auto-signature")
        or request.headers.get("x-hub-signature-256")
        or ""
    )
    if signature.lower().startswith("sha256="):
        signature = signature.split("=", 1)[1]
    return signature.strip()


def _bbc_return_page(settlement: Any) -> tuple[str, str, str]:
    """What the payer sees after the payment page; never internal ids or reasons."""
    status = settlement.status
    error = str(settlement.error_message or "")
    if status == SettlementStatus.SETTLED.value:
        return "ok", "پرداخت تأیید شد", "سرویس در تلگرام برای شما فرستاده شد."
    if error.startswith("review:") or status == SettlementStatus.FAILED.value:
        return (
            "warn",
            "پرداخت در حال بررسی است",
            "فروشگاه واریز را بررسی می‌کند و نتیجه در ربات به شما اطلاع داده می‌شود.",
        )
    if status == SettlementStatus.EXPIRED.value:
        return (
            "error",
            "مهلت پرداخت تمام شد",
            "به ربات برگردید و دوباره پرداخت را شروع کنید.",
        )
    return (
        "pending",
        "هنوز واریزی ثبت نشده",
        "بعد از واریز دقیقِ مبلغ یکتا، تأیید و تحویل خودکار انجام می‌شود.",
    )


def _register_mock_psp(app: Any, get_db: Callable[..., Any]) -> None:
    @app.get("/payments/settlement/mock/checkout", response_class=HTMLResponse)
    async def mock_checkout_page(
        request: Request,
        session: AsyncSession = Depends(get_db),
    ):
        from app.db.models import PaymentSettlement
        from app.services.payment_settlement import CHANNEL_PSP, settlement_mock_allowed

        if not settlement_mock_allowed():
            return Response(status_code=404, content="Not Found")

        sid = request.query_params.get("settlement_id") or ""
        token = (request.query_params.get("token") or "").strip()
        try:
            settlement_id = int(sid)
        except (TypeError, ValueError):
            return await _status(
                request,
                session,
                kind="error",
                title="درخواست نامعتبر",
                message="شناسه تسویه درست نیست.",
                http_status=400,
            )
        settlement = await session.get(PaymentSettlement, settlement_id)
        if (
            not settlement
            or settlement.channel != CHANNEL_PSP
            or settlement.provider != "mock"
        ):
            return await _status(
                request,
                session,
                kind="error",
                title="درخواست نامعتبر",
                message="این صفحه درگاه آزمایشی یافت نشد.",
                http_status=404,
                watermark="404",
            )
        from app.services.payment_settlement import _require_mock_token

        shop_id = settlement.shop_owner_id
        try:
            _require_mock_token(settlement, token)
        except ValueError:
            return await _status(
                request,
                session,
                shop_owner_id=shop_id,
                kind="error",
                title="درخواست نامعتبر",
                message="توکن این درگاه آزمایشی درست نیست.",
                http_status=403,
                watermark="403",
            )

        if settlement.status == SettlementStatus.SETTLED.value:
            return await _status(
                request,
                session,
                shop_owner_id=shop_id,
                kind="ok",
                title="قبلاً تسویه شده",
                message="این پرداخت پیش‌تر تأیید شده است.",
                watermark="OK",
            )

        amount = int(settlement.amount)
        body = f"""
<p>مبلغ: <b dir="ltr">{amount:,}</b> تومان</p>
<form method="post" action="/payments/settlement/mock/pay">
  <input type="hidden" name="settlement_id" value="{int(settlement.id)}"/>
  <input type="hidden" name="amount" value="{amount}"/>
  <input type="hidden" name="token" value="{escape(token)}"/>
  <button class="btn" type="submit">پرداخت آزمایشی موفق</button>
</form>
<p class="muted">فقط با ALLOW_SETTLEMENT_MOCK=1</p>
"""
        return await _status(
            request,
            session,
            shop_owner_id=shop_id,
            kind="pending",
            title="درگاه آزمایشی (Mock)",
            message="برای ادامه دکمهٔ زیر را بزنید.",
            watermark="MOCK",
            body_html=body,
        )

    @app.post("/payments/settlement/mock/pay", response_class=HTMLResponse)
    async def mock_pay(
        request: Request,
        settlement_id: int = Form(...),
        amount: int = Form(...),
        token: str = Form(...),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.payment_settlement import (
            deliver_psp_once,
            mock_psp_pay,
            settlement_mock_allowed,
        )

        if not settlement_mock_allowed():
            return Response(status_code=404, content="Not Found")
        try:
            settlement = await mock_psp_pay(
                session,
                settlement_id=settlement_id,
                amount=amount,
                token=token,
            )
        except ValueError:
            return await _status(
                request,
                session,
                kind="error",
                title="تسویه ناموفق",
                message="درخواست رد شد.",
                http_status=400,
            )
        if settlement.status == SettlementStatus.SETTLED.value:
            try:
                await deliver_psp_once(session, settlement)
            except Exception:
                logger.exception("mock pay notify failed settlement=%s", settlement.id)
        return await _status(
            request,
            session,
            shop_owner_id=settlement.shop_owner_id,
            kind="ok",
            title="پرداخت آزمایشی تأیید شد",
            message="نتیجه در ربات برایتان ارسال می‌شود؛ به چت ربات برگردید.",
            watermark="OK",
        )


def _register_psp_return(app: Any, get_db: Callable[..., Any]) -> None:
    @app.get("/payments/settlement/psp/{provider}/return/{settlement_id}")
    async def psp_return(
        provider: str,
        settlement_id: int,
        request: Request,
        session: AsyncSession = Depends(get_db),
    ):
        from app.db.models import PaymentSettlement
        from app.services.payment_settlement import (
            complete_psp_return,
            deliver_psp_once,
            settlement_mock_allowed,
        )

        provider_l = (provider or "").strip().lower()
        if provider_l == "mock" and not settlement_mock_allowed():
            return Response(status_code=404, content="Not Found")

        params = dict(request.query_params)
        pre = await session.get(PaymentSettlement, settlement_id)
        if not pre:
            return await _status(
                request,
                session,
                kind="error",
                title="تسویه یافت نشد",
                message="اگر مبلغ کم شده با پشتیبانی تماس بگیرید.",
                http_status=404,
                watermark="404",
            )
        reseller_id = pre.shop_owner_id

        try:
            settlement = await complete_psp_return(
                session,
                provider=provider_l,
                settlement_id=settlement_id,
                callback_params=params,
                reseller_id=reseller_id,
            )
        except ValueError:
            return await _status(
                request,
                session,
                shop_owner_id=reseller_id,
                kind="error",
                title="تأیید پرداخت ناموفق",
                message="اگر مبلغ کم شده با پشتیبانی تماس بگیرید.",
                http_status=400,
            )
        if settlement.status == SettlementStatus.SETTLED.value:
            try:
                await deliver_psp_once(session, settlement)
            except Exception:
                logger.exception("psp return notify failed settlement=%s", settlement.id)
            return await _status(
                request,
                session,
                shop_owner_id=settlement.shop_owner_id,
                kind="ok",
                title="پرداخت تأیید شد",
                message="نتیجه در ربات برایتان ارسال می‌شود؛ به چت ربات برگردید.",
                watermark="OK",
            )
        if settlement.status == SettlementStatus.AWAITING.value:
            return await _status(
                request,
                session,
                shop_owner_id=settlement.shop_owner_id,
                kind="pending",
                title="پرداخت هنوز تأیید نشده",
                message=(
                    "اگر پرداخت را کامل کردید به ربات برگردید؛ "
                    "تأیید خودکار است و لازم نیست این صفحه باز بماند."
                ),
                watermark="…",
            )
        return await _status(
            request,
            session,
            shop_owner_id=settlement.shop_owner_id,
            kind="warn",
            title="پرداخت تکمیل نشد",
            message=(
                "به ربات برگردید. اگر مبلغ کم شده، نتیجه آنجا اعلام می‌شود."
            ),
            watermark="!",
        )


def _register_card_auto(app: Any, get_db: Callable[..., Any]) -> None:
    async def _card_auto_webhook_for_shop(
        request: Request,
        session: AsyncSession,
        *,
        shop_owner_id: int | None,
    ):
        from app.db.models import Order, Payment
        from app.services.payment_settlement import (
            handle_card_auto_webhook,
            notify_after_settlement,
        )

        body = await request.body()
        if len(body) > 64 * 1024:
            return JSONResponse({"ok": False}, status_code=413)
        try:
            settlement = await handle_card_auto_webhook(
                session,
                body=body,
                signature=_sig_from_headers(request),
                shop_owner_id=shop_owner_id,
            )
        except ValueError as exc:
            logger.info("card-auto webhook rejected shop=%s: %s", shop_owner_id, exc)
            return JSONResponse({"ok": False}, status_code=400)
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
                "status": settlement.status,
            }
        )

    @app.post("/payments/settlement/card-auto/platform/webhook")
    async def card_auto_webhook_platform(
        request: Request,
        session: AsyncSession = Depends(get_db),
    ):
        return await _card_auto_webhook_for_shop(request, session, shop_owner_id=None)

    @app.post("/payments/settlement/card-auto/shop/{reseller_id}/webhook")
    async def card_auto_webhook_shop(
        reseller_id: int,
        request: Request,
        session: AsyncSession = Depends(get_db),
    ):
        from app.db.models import BotUser, Role

        if reseller_id <= 0:
            return JSONResponse({"ok": False}, status_code=404)
        owner = await session.get(BotUser, int(reseller_id))
        if not owner or owner.role != Role.RESELLER.value:
            return JSONResponse({"ok": False}, status_code=404)
        return await _card_auto_webhook_for_shop(
            request, session, shop_owner_id=int(reseller_id)
        )

    @app.api_route(
        "/payments/settlement/card-auto/webhook",
        methods=["GET", "POST"],
    )
    async def card_auto_webhook_legacy_removed():
        return JSONResponse(
            {
                "ok": False,
                "error": "use /card-auto/platform/webhook or /card-auto/shop/{id}/webhook",
            },
            status_code=410,
        )


def _register_bbc(app: Any, get_db: Callable[..., Any]) -> None:
    async def _bbc_finish(
        request: Request,
        session: AsyncSession,
        *,
        tenant_key: int,
        settlement_id: int,
        token: str,
        as_html: bool,
    ):
        from app.services.bbc_settlement import handle_bbc_link

        try:
            settlement = await handle_bbc_link(
                session, settlement_id=settlement_id, tenant_key=tenant_key, token=token
            )
        except ValueError:
            logger.info("bbc link rejected tenant=%s settlement=%s", tenant_key, settlement_id)
            if as_html:
                shop_id = int(tenant_key) if int(tenant_key) > 0 else None
                return await _status(
                    request,
                    session,
                    shop_owner_id=shop_id,
                    kind="error",
                    title="این لینک پرداخت معتبر نیست",
                    message="به ربات برگردید و وضعیت سفارش را آنجا ببینید.",
                    http_status=404,
                    watermark="404",
                )
            return JSONResponse({"ok": False}, status_code=404)
        if not as_html:
            return JSONResponse({"ok": True})
        kind, title, message = _bbc_return_page(settlement)
        return await _status(
            request,
            session,
            shop_owner_id=settlement.shop_owner_id,
            kind=kind,
            title=title,
            message=message,
            watermark="OK" if kind == "ok" else kind.upper()[:4],
        )

    @app.api_route(
        "/payments/settlement/bbc/tenant/{tenant_key}/callback/{settlement_id}",
        methods=["GET", "POST"],
    )
    async def bbc_callback(
        tenant_key: int,
        settlement_id: int,
        request: Request,
        session: AsyncSession = Depends(get_db),
    ):
        token = (request.query_params.get("t") or "").strip()
        return await _bbc_finish(
            request,
            session,
            tenant_key=tenant_key,
            settlement_id=settlement_id,
            token=token,
            as_html=False,
        )

    @app.get("/payments/settlement/bbc/tenant/{tenant_key}/return/{settlement_id}")
    async def bbc_return(
        tenant_key: int,
        settlement_id: int,
        request: Request,
        session: AsyncSession = Depends(get_db),
    ):
        token = (request.query_params.get("t") or "").strip()
        return await _bbc_finish(
            request,
            session,
            tenant_key=tenant_key,
            settlement_id=settlement_id,
            token=token,
            as_html=True,
        )


def register_settlement_pages(app, *, get_db):
    _register_mock_psp(app, get_db)
    _register_psp_return(app, get_db)
    _register_card_auto(app, get_db)
    _register_bbc(app, get_db)
