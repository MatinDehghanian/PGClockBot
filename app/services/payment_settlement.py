"""Payment Settlement Core — additive, fail-closed, tenant-isolated, idempotent.

Channels:
  - psp: Iranian/online gateway (mock gated by env / zarinpal / …)
  - card_auto: signed webhook from card-confirm providers (per-tenant secret)

Existing wallet / card+receipt / gateway-link / crypto / stars paths are untouched.
Success always ends in ``approve_payment``.
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    BotUser,
    Order,
    Payment,
    PaymentSettlement,
    PaymentStatus,
    SettlementStatus,
)
from app.services.orders import approve_payment
from app.services.payment_providers import get_psp_adapter
from app.services.payment_providers.base import CheckoutRequest
from app.services.payment_providers.card_auto import (
    parse_card_auto_event,
    verify_signature,
)
from app.services.users import get_all_settings

logger = logging.getLogger(__name__)

CHANNEL_PSP = "psp"
CHANNEL_CARD_AUTO = "card_auto"


def _public_base() -> str:
    cfg = get_settings()
    return (cfg.public_base_url or cfg.webhook_url or "").rstrip("/")


def _on(val: str | None) -> bool:
    return str(val or "").strip().lower() in {"1", "true", "yes", "on"}


def settlement_mock_allowed() -> bool:
    """Mock settle is OFF by default. Enable only via ALLOW_SETTLEMENT_MOCK=1."""
    try:
        return bool(get_settings().allow_settlement_mock)
    except Exception:
        return False


def _shop_ids_equal(a: int | None, b: int | None) -> bool:
    return (a if a is not None else None) == (b if b is not None else None)


async def resolve_payment_shop_owner_id(
    session: AsyncSession, payment: Payment
) -> int | None:
    """Tenant of a payment: order.reseller_id, else payer.reseller_id, else platform (None)."""
    if payment.order_id:
        order = await session.get(Order, int(payment.order_id))
        if order and order.reseller_id:
            return int(order.reseller_id)
        return None
    user = await session.get(BotUser, int(payment.user_id))
    if user and user.reseller_id:
        return int(user.reseller_id)
    return None


async def assert_payment_in_shop(
    session: AsyncSession,
    payment: Payment,
    *,
    shop_owner_id: int | None,
) -> None:
    actual = await resolve_payment_shop_owner_id(session, payment)
    if not _shop_ids_equal(actual, shop_owner_id):
        raise ValueError("پرداخت خارج از محدوده فروشگاه است")


async def create_psp_checkout(
    session: AsyncSession,
    payment: Payment,
    *,
    reseller_id: int | None = None,
    description: str = "",
) -> PaymentSettlement:
    """Create a PSP settlement + checkout URL for a pending payment."""
    if payment.status != PaymentStatus.PENDING.value:
        raise ValueError("پرداخت قابل شروع درگاه نیست")
    if int(payment.amount) <= 0:
        raise ValueError("مبلغ نامعتبر")

    shop_owner_id = await resolve_payment_shop_owner_id(session, payment)
    # Caller context must not claim another tenant's payment.
    if reseller_id is not None and not _shop_ids_equal(shop_owner_id, int(reseller_id)):
        raise ValueError("پرداخت خارج از محدوده فروشگاه است")

    ui = await get_all_settings(session, reseller_id=shop_owner_id)
    if not _on(ui.get("pay_psp_enabled")):
        raise ValueError("پرداخت درگاه API غیرفعال است")

    existing = (
        await session.execute(
            select(PaymentSettlement)
            .where(
                PaymentSettlement.payment_id == int(payment.id),
                PaymentSettlement.channel == CHANNEL_PSP,
                PaymentSettlement.status == SettlementStatus.AWAITING.value,
            )
            .order_by(PaymentSettlement.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing and (existing.checkout_url or "").strip():
        return existing

    provider = str(ui.get("psp_provider") or "zarinpal").strip().lower() or "zarinpal"
    if provider == "mock" and not settlement_mock_allowed():
        raise ValueError(
            "درگاه mock فقط با ALLOW_SETTLEMENT_MOCK=1 فعال است — provider را zarinpal بگذارید"
        )

    base = _public_base()
    if not base and provider != "mock":
        raise ValueError("PUBLIC_BASE_URL برای بازگشت درگاه تنظیم نشده")
    if not base:
        base = "http://127.0.0.1:8000"

    checkout_token = secrets.token_urlsafe(24)
    idem = f"psp:{payment.id}:{secrets.token_hex(8)}"
    settlement = PaymentSettlement(
        payment_id=int(payment.id),
        shop_owner_id=shop_owner_id,
        channel=CHANNEL_PSP,
        provider=provider,
        status=SettlementStatus.CREATED.value,
        amount=int(payment.amount),
        currency="IRT",
        idempotency_key=idem,
        checkout_token=checkout_token,
    )
    session.add(settlement)
    await session.flush()

    adapter = get_psp_adapter(provider, ui=ui, public_base_url=base)
    callback_url = f"{base}/payments/settlement/psp/{provider}/return/{int(settlement.id)}"
    if provider == "mock":
        callback_url = f"{callback_url}?token={checkout_token}"
    req = CheckoutRequest(
        settlement_id=int(settlement.id),
        payment_id=int(payment.id),
        amount=int(payment.amount),
        currency="IRT",
        description=description or f"order-payment-{payment.id}",
        callback_url=callback_url,
        return_url=callback_url,
        metadata={"payment_id": int(payment.id)},
    )
    try:
        result = await adapter.create_checkout(req)
    except Exception as exc:
        settlement.status = SettlementStatus.FAILED.value
        settlement.error_message = str(exc)[:500]
        await session.commit()
        raise

    # Mock adapter must embed the one-time token (not guessable id alone).
    checkout_url = result.checkout_url
    if provider == "mock":
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        parts = urlsplit(checkout_url)
        q = dict(parse_qsl(parts.query, keep_blank_values=True))
        q["token"] = checkout_token
        checkout_url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment)
        )

    settlement.external_ref = result.external_ref[:128]
    settlement.checkout_url = checkout_url
    settlement.provider_payload = json.dumps(result.raw or {}, ensure_ascii=False)[:4000]
    settlement.status = SettlementStatus.AWAITING.value
    if not payment.receipt_file_id:
        payment.receipt_file_id = f"psp:{provider}:{result.external_ref}"[:255]
    await session.commit()
    await session.refresh(settlement)
    return settlement


async def create_card_auto_awaiting(
    session: AsyncSession,
    payment: Payment,
    *,
    reseller_id: int | None = None,
) -> PaymentSettlement:
    """Register a card payment for automatic confirm via provider webhook."""
    if payment.status != PaymentStatus.PENDING.value:
        raise ValueError("پرداخت قابل ثبت نیست")

    shop_owner_id = await resolve_payment_shop_owner_id(session, payment)
    if reseller_id is not None and not _shop_ids_equal(shop_owner_id, int(reseller_id)):
        raise ValueError("پرداخت خارج از محدوده فروشگاه است")

    ui = await get_all_settings(session, reseller_id=shop_owner_id)
    if not _on(ui.get("pay_card_auto_enabled")):
        raise ValueError("تأیید خودکار کارت غیرفعال است")
    secret = str(ui.get("card_auto_webhook_secret") or "").strip()
    if not secret or len(secret) < 16:
        raise ValueError("رمز وب‌هوک کارت خودکار تنظیم نشده یا خیلی کوتاه است")

    provider = str(ui.get("card_auto_provider") or "generic").strip().lower() or "generic"
    idem = f"cardauto:{payment.id}:{secrets.token_hex(8)}"
    settlement = PaymentSettlement(
        payment_id=int(payment.id),
        shop_owner_id=shop_owner_id,
        channel=CHANNEL_CARD_AUTO,
        provider=provider,
        status=SettlementStatus.AWAITING.value,
        amount=int(payment.amount),
        currency="IRT",
        idempotency_key=idem,
        external_ref=None,
    )
    session.add(settlement)
    if not payment.receipt_file_id:
        payment.receipt_file_id = f"card_auto:awaiting:{payment.id}"[:255]
    await session.commit()
    await session.refresh(settlement)
    return settlement


async def _mark_settled(
    session: AsyncSession,
    settlement: PaymentSettlement,
    *,
    external_ref: str | None = None,
) -> PaymentSettlement:
    """Idempotent transition → SETTLED. Returns settlement (may already be settled)."""
    sid = int(settlement.id)
    values: dict[str, Any] = {
        "status": SettlementStatus.SETTLED.value,
        "settled_at": datetime.now(timezone.utc),
        "error_message": None,
        "checkout_token": None,  # consume one-time mock token
    }
    if external_ref:
        values["external_ref"] = external_ref[:128]
    with session.no_autoflush:
        claim = await session.execute(
            update(PaymentSettlement)
            .where(
                PaymentSettlement.id == sid,
                PaymentSettlement.status.in_(
                    (
                        SettlementStatus.CREATED.value,
                        SettlementStatus.AWAITING.value,
                    )
                ),
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
    await session.refresh(settlement)
    if claim.rowcount != 1:
        if settlement.status == SettlementStatus.SETTLED.value:
            return settlement
        raise ValueError("این تسویه قابل تأیید نیست")
    return settlement


async def settle_and_approve(
    session: AsyncSession,
    settlement: PaymentSettlement,
    *,
    expected_amount: int,
    external_ref: str | None = None,
    reviewer_tg: int = 0,
) -> Payment:
    """Fail-closed settle: amount must match; then approve_payment once."""
    if int(expected_amount) != int(settlement.amount):
        settlement.status = SettlementStatus.FAILED.value
        settlement.error_message = "amount mismatch"
        await session.commit()
        raise ValueError("مبلغ با تسویه هم‌خوانی ندارد")

    payment = await session.get(Payment, int(settlement.payment_id))
    if not payment:
        raise ValueError("پرداخت یافت نشد")
    if int(payment.amount) != int(settlement.amount):
        settlement.status = SettlementStatus.FAILED.value
        settlement.error_message = "payment amount mismatch"
        await session.commit()
        raise ValueError("مبلغ پرداخت با تسویه هم‌خوانی ندارد")

    # Tenant binding: settlement shop must match payment shop.
    pay_shop = await resolve_payment_shop_owner_id(session, payment)
    if not _shop_ids_equal(pay_shop, settlement.shop_owner_id):
        settlement.status = SettlementStatus.FAILED.value
        settlement.error_message = "shop ownership mismatch"
        await session.commit()
        raise ValueError("ناسازگاری محدوده فروشگاه")

    await _mark_settled(session, settlement, external_ref=external_ref)

    if payment.status == PaymentStatus.APPROVED.value:
        await session.commit()
        return payment

    if payment.status != PaymentStatus.PENDING.value:
        raise ValueError("وضعیت پرداخت برای تسویه مناسب نیست")

    if not payment.receipt_file_id or str(payment.receipt_file_id).startswith("card_auto:awaiting"):
        ref = external_ref or settlement.external_ref or str(settlement.id)
        payment.receipt_file_id = f"{settlement.channel}:{settlement.provider}:{ref}"[:255]

    try:
        await approve_payment(session, payment, reviewer_tg=reviewer_tg)
    except ValueError as exc:
        if "قبلاً تأیید شده" in str(exc):
            await session.refresh(payment)
            return payment
        settlement.status = SettlementStatus.FAILED.value
        settlement.error_message = str(exc)[:500]
        await session.commit()
        raise

    await session.refresh(payment)
    return payment


def _require_mock_token(settlement: PaymentSettlement, token: str | None) -> None:
    expected = (settlement.checkout_token or "").strip()
    got = (token or "").strip()
    if not expected or not got or len(expected) != len(got):
        raise ValueError("توکن تسویه نامعتبر است")
    if not hmac.compare_digest(expected, got):
        raise ValueError("توکن تسویه نامعتبر است")


async def complete_psp_return(
    session: AsyncSession,
    *,
    provider: str,
    settlement_id: int,
    callback_params: dict[str, Any],
    reseller_id: int | None = None,
) -> PaymentSettlement:
    provider = (provider or "").strip().lower()
    if provider == "mock" and not settlement_mock_allowed():
        raise ValueError("تسویه mock غیرفعال است")

    settlement = await session.get(PaymentSettlement, int(settlement_id))
    if not settlement or settlement.channel != CHANNEL_PSP:
        raise ValueError("تسویه یافت نشد")
    if settlement.provider != provider:
        raise ValueError("ارائه‌دهنده ناسازگار است")
    if not _shop_ids_equal(settlement.shop_owner_id, reseller_id):
        raise ValueError("محدوده فروشگاه ناسازگار است")
    if settlement.status == SettlementStatus.SETTLED.value:
        return settlement

    if provider == "mock":
        _require_mock_token(settlement, str(callback_params.get("token") or ""))

    ui = await get_all_settings(session, reseller_id=settlement.shop_owner_id)
    if not _on(ui.get("pay_psp_enabled")):
        raise ValueError("پرداخت درگاه API غیرفعال است")

    base = _public_base() or "http://127.0.0.1:8000"
    adapter = get_psp_adapter(provider, ui=ui, public_base_url=base)
    external_ref = settlement.external_ref or str(
        callback_params.get("Authority")
        or callback_params.get("authority")
        or callback_params.get("external_ref")
        or ""
    )
    if not external_ref:
        raise ValueError("شناسه تراکنش موجود نیست")
    # Authority in callback must match the settlement we created (anti-swap).
    if settlement.external_ref and str(settlement.external_ref).lower() != str(external_ref).lower():
        raise ValueError("شناسه تراکنش با تسویه هم‌خوانی ندارد")

    verified = await adapter.verify(
        external_ref=external_ref,
        amount=int(settlement.amount),
        callback_params=callback_params,
    )
    if not verified.ok:
        settlement.status = SettlementStatus.FAILED.value
        settlement.error_message = (verified.message or "verify failed")[:500]
        await session.commit()
        raise ValueError(verified.message or "تأیید درگاه ناموفق بود")

    paid_amount = verified.amount if verified.amount is not None else settlement.amount
    await settle_and_approve(
        session,
        settlement,
        expected_amount=int(paid_amount),
        external_ref=verified.external_ref or external_ref,
        reviewer_tg=0,
    )
    await session.refresh(settlement)
    return settlement


async def handle_card_auto_webhook(
    session: AsyncSession,
    *,
    body: bytes,
    signature: str,
    shop_owner_id: int | None,
) -> PaymentSettlement:
    """Handle signed card-auto event for one tenant (platform or one reseller).

    ``shop_owner_id`` is taken from the URL path — never from the JSON body.
    ``payment_id`` is required (no cross-tenant amount-only matching).
    """
    ui = await get_all_settings(session, reseller_id=shop_owner_id)
    if not _on(ui.get("pay_card_auto_enabled")):
        raise ValueError("تأیید خودکار کارت غیرفعال است")
    secret = str(ui.get("card_auto_webhook_secret") or "").strip()
    if not secret or len(secret) < 16:
        raise ValueError("رمز وب‌هوک کارت خودکار تنظیم نشده")
    if not verify_signature(secret=secret, body=body, signature=signature):
        raise ValueError("امضای وب‌هوک نامعتبر است")

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("JSON نامعتبر") from exc

    event = parse_card_auto_event(payload)
    if not event.payment_id:
        raise ValueError("payment_id الزامی است")

    provider = str(ui.get("card_auto_provider") or "generic").strip().lower() or "generic"

    existing = (
        await session.execute(
            select(PaymentSettlement).where(
                PaymentSettlement.provider == provider,
                PaymentSettlement.external_ref == event.external_ref,
                PaymentSettlement.channel == CHANNEL_CARD_AUTO,
                PaymentSettlement.status == SettlementStatus.SETTLED.value,
                *(
                    (PaymentSettlement.shop_owner_id.is_(None),)
                    if shop_owner_id is None
                    else (PaymentSettlement.shop_owner_id == int(shop_owner_id),)
                ),
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    payment = await session.get(Payment, int(event.payment_id))
    if not payment:
        raise ValueError("پرداخت یافت نشد")
    await assert_payment_in_shop(session, payment, shop_owner_id=shop_owner_id)

    if payment.status != PaymentStatus.PENDING.value:
        raise ValueError("پرداخت در وضعیت مناسب نیست")
    if int(payment.amount) != int(event.amount):
        raise ValueError("مبلغ با پرداخت هم‌خوانی ندارد")

    settle_filters = [
        PaymentSettlement.payment_id == int(payment.id),
        PaymentSettlement.channel == CHANNEL_CARD_AUTO,
        PaymentSettlement.status == SettlementStatus.AWAITING.value,
    ]
    if shop_owner_id is None:
        settle_filters.append(PaymentSettlement.shop_owner_id.is_(None))
    else:
        settle_filters.append(PaymentSettlement.shop_owner_id == int(shop_owner_id))

    settlement = (
        await session.execute(
            select(PaymentSettlement)
            .where(*settle_filters)
            .order_by(PaymentSettlement.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not settlement:
        settlement = PaymentSettlement(
            payment_id=int(payment.id),
            shop_owner_id=shop_owner_id,
            channel=CHANNEL_CARD_AUTO,
            provider=provider,
            status=SettlementStatus.AWAITING.value,
            amount=int(payment.amount),
            currency="IRT",
            idempotency_key=f"cardauto:hook:{payment.id}:{event.external_ref}"[:64],
        )
        session.add(settlement)
        await session.flush()
    elif not _shop_ids_equal(settlement.shop_owner_id, shop_owner_id):
        raise ValueError("محدوده فروشگاه ناسازگار است")

    await settle_and_approve(
        session,
        settlement,
        expected_amount=int(event.amount),
        external_ref=event.external_ref,
        reviewer_tg=0,
    )
    await session.refresh(settlement)
    return settlement


async def mock_psp_pay(
    session: AsyncSession,
    *,
    settlement_id: int,
    amount: int,
    token: str,
) -> PaymentSettlement:
    """Test helper: settle mock checkout. Requires ALLOW_SETTLEMENT_MOCK + token."""
    if not settlement_mock_allowed():
        raise ValueError("تسویه mock غیرفعال است")
    settlement = await session.get(PaymentSettlement, int(settlement_id))
    if not settlement or settlement.provider != "mock" or settlement.channel != CHANNEL_PSP:
        raise ValueError("تسویه mock یافت نشد")
    return await complete_psp_return(
        session,
        provider="mock",
        settlement_id=int(settlement_id),
        callback_params={
            "status": "ok",
            "amount": int(amount),
            "token": token,
            "external_ref": settlement.external_ref or f"mock-{settlement_id}",
        },
        reseller_id=settlement.shop_owner_id,
    )


async def notify_after_settlement(
    session: AsyncSession,
    payment: Payment,
    order,
) -> None:
    """Best-effort Telegram delivery after automated settle (shared with panel approve)."""
    from app.db.models import Plan
    from app.services.delivery import send_delivery_to_user
    from app.services.notifications import notify_new_subscription, notify_wallet_topup_ok
    from app.services.reseller_bots import open_notify_bot_for_user

    user = await session.get(BotUser, payment.user_id)
    if not user:
        return
    bot, should_close = await open_notify_bot_for_user(session, user)
    try:
        try:
            await send_delivery_to_user(bot, user.telegram_id, session, payment, order)
        except Exception as send_exc:
            if order is not None:
                try:
                    from app.services.ux20 import note_delivery_send_failure

                    await note_delivery_send_failure(
                        session, order=order, payment=payment, error=str(send_exc)
                    )
                except Exception:
                    pass
            raise
        if payment.is_wallet_topup:
            await notify_wallet_topup_ok(bot, session, payment, user.telegram_id)
        elif order:
            plan = await session.get(Plan, order.plan_id) if order.plan_id else None
            await notify_new_subscription(
                bot,
                session,
                order=order,
                user_tg_id=user.telegram_id,
                user_name=user.full_name or user.username,
                plan_name=plan.name if plan else None,
                needs_approval=False,
            )
    finally:
        if should_close:
            try:
                await bot.session.close()
            except Exception:
                pass
