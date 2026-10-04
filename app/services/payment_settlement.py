"""Payment Settlement Core — additive, fail-closed, tenant-isolated, idempotent.

Channels:
  - psp: Iranian/online gateway (mock gated by env / zarinpal / …)
  - card_auto: signed webhook from card-confirm providers (per-tenant secret)

Existing wallet / card+receipt / gateway-link / crypto / stars paths are untouched.
Success always ends in ``approve_payment`` — settlement becomes SETTLED only after approve.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
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

_OPEN_STATUSES = (
    SettlementStatus.CREATED.value,
    SettlementStatus.AWAITING.value,
    SettlementStatus.SETTLING.value,
)


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


def tenant_key_for(shop_owner_id: int | None) -> int:
    return int(shop_owner_id) if shop_owner_id is not None else 0


def idem_key_psp(payment_id: int) -> str:
    return f"psp:{int(payment_id)}"


def idem_key_card_auto(payment_id: int) -> str:
    return f"cardauto:{int(payment_id)}"


async def resolve_payment_shop_owner_id(
    session: AsyncSession, payment: Payment
) -> int | None:
    """Tenant of a payment for settlement keys / HMAC.

    Order payments use ``order.reseller_id``. Wallet top-ups use the shop
    captured at creation (``payment.wallet_shop_id``) — never sticky
    ``user.reseller_id``, which let a shop webhook mint platform balance.
    """
    if payment.is_wallet_topup:
        wid = getattr(payment, "wallet_shop_id", None)
        return int(wid) if wid else None
    if payment.order_id:
        order = await session.get(Order, int(payment.order_id))
        if order and order.reseller_id:
            return int(order.reseller_id)
        return None
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


async def _get_by_idem(
    session: AsyncSession, key: str
) -> PaymentSettlement | None:
    return (
        await session.execute(
            select(PaymentSettlement)
            .where(PaymentSettlement.idempotency_key == key)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def _get_open_for_payment_channel(
    session: AsyncSession, *, payment_id: int, channel: str
) -> PaymentSettlement | None:
    return (
        await session.execute(
            select(PaymentSettlement)
            .where(
                PaymentSettlement.payment_id == int(payment_id),
                PaymentSettlement.channel == channel,
                PaymentSettlement.status.in_(_OPEN_STATUSES),
            )
            .order_by(PaymentSettlement.id.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


def _embed_mock_token(checkout_url: str, token: str) -> str:
    parts = urlsplit(checkout_url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q["token"] = token
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))


async def _break_read_snapshot(session: AsyncSession) -> None:
    """End the current txn so peer commits become visible (needed on SQLite).

    SQLite DEFERRED transactions keep a read snapshot for the whole txn; without
    ending it, a loser waiting on a concurrent winner never sees AWAITING+url.
    ``commit()`` persists any prior caller dirty state (SAVEPOINT already
    protected the failed insert) rather than wiping it with rollback.
    """
    bind = session.get_bind()
    if bind is not None and getattr(bind.dialect, "name", "") == "sqlite":
        await session.commit()


async def _await_open_settlement(
    session: AsyncSession,
    *,
    idem: str,
    payment_id: int,
    channel: str,
    require_checkout_url: bool = False,
    attempts: int = 80,
    delay_s: float = 0.05,
) -> PaymentSettlement | None:
    """Poll for the winner row after a lost insert race (same DB, other session)."""
    for _ in range(max(1, attempts)):
        await _break_read_snapshot(session)
        raced = await _get_by_idem(session, idem) or await _get_open_for_payment_channel(
            session, payment_id=payment_id, channel=channel
        )
        if raced is None:
            await asyncio.sleep(delay_s)
            continue
        if raced.status == SettlementStatus.FAILED.value:
            return raced
        if raced.status == SettlementStatus.SETTLED.value:
            return raced
        if raced.status == SettlementStatus.SETTLING.value:
            return raced
        if require_checkout_url:
            if raced.status == SettlementStatus.AWAITING.value and (raced.checkout_url or "").strip():
                return raced
        elif raced.status in _OPEN_STATUSES or raced.status == SettlementStatus.AWAITING.value:
            return raced
        await asyncio.sleep(delay_s)
    await _break_read_snapshot(session)
    raced = await _get_by_idem(session, idem) or await _get_open_for_payment_channel(
        session, payment_id=payment_id, channel=channel
    )
    if raced is None:
        return None
    if require_checkout_url:
        if raced.status == SettlementStatus.AWAITING.value and (raced.checkout_url or "").strip():
            return raced
        if raced.status in {
            SettlementStatus.FAILED.value,
            SettlementStatus.SETTLING.value,
            SettlementStatus.SETTLED.value,
        }:
            return raced
        return None
    return raced


async def _insert_settlement_race_safe(
    session: AsyncSession, settlement: PaymentSettlement
) -> PaymentSettlement:
    """INSERT with SAVEPOINT — on conflict return the winning row (no full rollback)."""
    try:
        async with session.begin_nested():
            session.add(settlement)
            await session.flush()
        return settlement
    except IntegrityError:
        # SAVEPOINT rollback may already detach the failed instance.
        if settlement in session:
            session.expunge(settlement)
        idem = settlement.idempotency_key
        payment_id = int(settlement.payment_id)
        channel = str(settlement.channel)
        await _break_read_snapshot(session)
        raced = await _get_by_idem(session, idem)
        if raced is None:
            raced = await _get_open_for_payment_channel(
                session, payment_id=payment_id, channel=channel
            )
        if raced is None:
            # Peer may still hold an uncommitted insert — poll briefly.
            raced = await _await_open_settlement(
                session,
                idem=idem,
                payment_id=payment_id,
                channel=channel,
                require_checkout_url=False,
            )
        if raced is None:
            raise ValueError("ساخت تسویه همزمان ناموفق بود — دوباره تلاش کنید")
        return raced


async def create_psp_checkout(
    session: AsyncSession,
    payment: Payment,
    *,
    reseller_id: int | None = None,
    description: str = "",
) -> PaymentSettlement:
    """Create or reuse the single open PSP settlement for this payment (race-safe)."""
    if payment.status != PaymentStatus.PENDING.value:
        raise ValueError("پرداخت قابل شروع درگاه نیست")
    if int(payment.amount) <= 0:
        raise ValueError("مبلغ نامعتبر")

    shop_owner_id = await resolve_payment_shop_owner_id(session, payment)
    if reseller_id is not None and not _shop_ids_equal(shop_owner_id, int(reseller_id)):
        raise ValueError("پرداخت خارج از محدوده فروشگاه است")

    ui = await get_all_settings(session, reseller_id=shop_owner_id)
    if not _on(ui.get("pay_psp_enabled")):
        raise ValueError("پرداخت درگاه API غیرفعال است")

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

    idem = idem_key_psp(int(payment.id))
    existing = await _get_by_idem(session, idem)
    if existing is None:
        existing = await _get_open_for_payment_channel(
            session, payment_id=int(payment.id), channel=CHANNEL_PSP
        )

    if existing:
        if existing.status == SettlementStatus.SETTLED.value:
            return existing
        if existing.status == SettlementStatus.SETTLING.value:
            return existing
        if existing.status == SettlementStatus.AWAITING.value and (existing.checkout_url or "").strip():
            return existing
        # FAILED / CREATED without URL / stale → reuse same row (deterministic key).
        settlement = existing
        settlement.shop_owner_id = shop_owner_id
        settlement.tenant_key = tenant_key_for(shop_owner_id)
        settlement.provider = provider
        settlement.amount = int(payment.amount)
        settlement.status = SettlementStatus.CREATED.value
        settlement.error_message = None
        settlement.external_ref = None
        settlement.checkout_url = None
        settlement.provider_payload = None
        settlement.settled_at = None
        settlement.checkout_token = secrets.token_urlsafe(24)
    else:
        candidate = PaymentSettlement(
            payment_id=int(payment.id),
            shop_owner_id=shop_owner_id,
            tenant_key=tenant_key_for(shop_owner_id),
            channel=CHANNEL_PSP,
            provider=provider,
            status=SettlementStatus.CREATED.value,
            amount=int(payment.amount),
            currency="IRT",
            idempotency_key=idem,
            checkout_token=secrets.token_urlsafe(24),
        )
        inserted = await _insert_settlement_race_safe(session, candidate)
        if inserted is not candidate:
            # Lost insert race — never roll back caller; wait for winner checkout.
            try:
                await session.refresh(inserted)
            except Exception:
                inserted = await _get_by_idem(session, idem) or inserted
            if inserted is not None and inserted.status == SettlementStatus.AWAITING.value and (
                inserted.checkout_url or ""
            ).strip():
                return inserted
            if inserted is not None and inserted.status in {
                SettlementStatus.SETTLING.value,
                SettlementStatus.SETTLED.value,
            }:
                return inserted
            raced = await _await_open_settlement(
                session,
                idem=idem,
                payment_id=int(payment.id),
                channel=CHANNEL_PSP,
                require_checkout_url=True,
            )
            if raced is None:
                raise ValueError("ساخت تسویه همزمان ناموفق بود — دوباره تلاش کنید")
            if raced.status == SettlementStatus.FAILED.value:
                return raced
            if raced.status in {
                SettlementStatus.SETTLING.value,
                SettlementStatus.SETTLED.value,
            }:
                return raced
            if (raced.checkout_url or "").strip():
                return raced
            raise ValueError("ساخت تسویه همزمان ناموفق بود — دوباره تلاش کنید")
        settlement = inserted

    adapter = get_psp_adapter(provider, ui=ui, public_base_url=base)
    token = settlement.checkout_token or secrets.token_urlsafe(24)
    settlement.checkout_token = token
    callback_url = f"{base}/payments/settlement/psp/{provider}/return/{int(settlement.id)}"
    if provider == "mock":
        callback_url = f"{callback_url}?token={token}"
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

    checkout_url = result.checkout_url
    if provider == "mock":
        checkout_url = _embed_mock_token(checkout_url, token)

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
    """Register (or reuse) the single open card-auto settlement for this payment."""
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
    idem = idem_key_card_auto(int(payment.id))
    existing = await _get_by_idem(session, idem)
    if existing is None:
        existing = await _get_open_for_payment_channel(
            session, payment_id=int(payment.id), channel=CHANNEL_CARD_AUTO
        )
    if existing:
        if existing.status in {
            SettlementStatus.AWAITING.value,
            SettlementStatus.SETTLING.value,
            SettlementStatus.SETTLED.value,
        }:
            return existing
        existing.shop_owner_id = shop_owner_id
        existing.tenant_key = tenant_key_for(shop_owner_id)
        existing.provider = provider
        existing.amount = int(payment.amount)
        existing.status = SettlementStatus.AWAITING.value
        existing.error_message = None
        existing.external_ref = None
        existing.settled_at = None
        await session.commit()
        await session.refresh(existing)
        return existing

    settlement = PaymentSettlement(
        payment_id=int(payment.id),
        shop_owner_id=shop_owner_id,
        tenant_key=tenant_key_for(shop_owner_id),
        channel=CHANNEL_CARD_AUTO,
        provider=provider,
        status=SettlementStatus.AWAITING.value,
        amount=int(payment.amount),
        currency="IRT",
        idempotency_key=idem,
        external_ref=None,
    )
    if not payment.receipt_file_id:
        payment.receipt_file_id = f"card_auto:awaiting:{payment.id}"[:255]
    inserted = await _insert_settlement_race_safe(session, settlement)
    if inserted is not settlement:
        await session.commit()
        return inserted
    await session.commit()
    await session.refresh(inserted)
    return inserted


async def _claim_for_settle(
    session: AsyncSession,
    settlement: PaymentSettlement,
    *,
    external_ref: str | None,
) -> tuple[PaymentSettlement, bool]:
    """Move created/awaiting → settling. Returns (row, won_claim).

    Only the caller with ``won_claim=True`` may call ``approve_payment``.
    Uses SAVEPOINT on IntegrityError (duplicate external_ref) — no full rollback.
    """
    sid = int(settlement.id)
    values: dict[str, Any] = {
        "status": SettlementStatus.SETTLING.value,
        "checkout_token": None,
        "error_message": None,
    }
    if external_ref:
        values["external_ref"] = external_ref[:128]
    try:
        async with session.begin_nested():
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
                await session.flush()
    except IntegrityError as exc:
        # Duplicate provider event under unique tenant_ext_ref — return winner.
        if external_ref:
            winner = (
                await session.execute(
                    select(PaymentSettlement).where(
                        PaymentSettlement.channel == settlement.channel,
                        PaymentSettlement.provider == settlement.provider,
                        PaymentSettlement.tenant_key == settlement.tenant_key,
                        PaymentSettlement.external_ref == external_ref[:128],
                        PaymentSettlement.status.in_(
                            (
                                SettlementStatus.SETTLING.value,
                                SettlementStatus.SETTLED.value,
                            )
                        ),
                    )
                )
            ).scalar_one_or_none()
            if winner:
                return winner, False
        raise ValueError("رویداد تکراری یا ناسازگار") from exc

    await session.refresh(settlement)
    if claim.rowcount == 1:
        return settlement, True
    if settlement.status in {
        SettlementStatus.SETTLING.value,
        SettlementStatus.SETTLED.value,
    }:
        return settlement, False
    raise ValueError("این تسویه قابل تأیید نیست")


async def _wait_for_peer_settle(
    session: AsyncSession,
    settlement: PaymentSettlement,
    payment: Payment,
) -> Payment:
    """Loser of claim: do not approve; wait for winner to finish."""
    sid = int(settlement.id)
    pid = int(payment.id)
    for _ in range(80):
        await _break_read_snapshot(session)
        # expire_on_commit=False keeps stale identity — force DB reload.
        settlement = (
            await session.execute(
                select(PaymentSettlement)
                .where(PaymentSettlement.id == sid)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        payment = (
            await session.execute(
                select(Payment)
                .where(Payment.id == pid)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        if settlement.status == SettlementStatus.SETTLED.value:
            return payment
        if payment.status == PaymentStatus.APPROVED.value:
            await _finalize_settled(session, settlement)
            await session.commit()
            return payment
        await asyncio.sleep(0.05)
    await _break_read_snapshot(session)
    settlement = (
        await session.execute(
            select(PaymentSettlement)
            .where(PaymentSettlement.id == sid)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    payment = (
        await session.execute(
            select(Payment).where(Payment.id == pid).execution_options(populate_existing=True)
        )
    ).scalar_one()
    if settlement.status == SettlementStatus.SETTLED.value:
        return payment
    if payment.status == PaymentStatus.APPROVED.value:
        await _finalize_settled(session, settlement)
        await session.commit()
        return payment
    raise ValueError("تسویه توسط درخواست دیگر در حال انجام است")


async def _finalize_settled(
    session: AsyncSession,
    settlement: PaymentSettlement,
) -> None:
    with session.no_autoflush:
        await session.execute(
            update(PaymentSettlement)
            .where(
                PaymentSettlement.id == int(settlement.id),
                PaymentSettlement.status.in_(
                    (
                        SettlementStatus.SETTLING.value,
                        SettlementStatus.AWAITING.value,
                        SettlementStatus.CREATED.value,
                    )
                ),
            )
            .values(
                status=SettlementStatus.SETTLED.value,
                settled_at=datetime.now(timezone.utc),
                checkout_token=None,
                error_message=None,
            )
            .execution_options(synchronize_session=False)
        )
    await session.refresh(settlement)


async def _revert_claim_to_awaiting(
    session: AsyncSession,
    settlement: PaymentSettlement,
    *,
    error: str,
) -> None:
    """Approve failed — leave retriable (not permanent SETTLED)."""
    with session.no_autoflush:
        await session.execute(
            update(PaymentSettlement)
            .where(
                PaymentSettlement.id == int(settlement.id),
                PaymentSettlement.status == SettlementStatus.SETTLING.value,
            )
            .values(
                status=SettlementStatus.AWAITING.value,
                error_message=error[:500],
            )
            .execution_options(synchronize_session=False)
        )
    await session.refresh(settlement)


async def settle_and_approve(
    session: AsyncSession,
    settlement: PaymentSettlement,
    *,
    expected_amount: int,
    external_ref: str | None = None,
    reviewer_tg: int = 0,
) -> Payment:
    """Fail-closed settle: amount/tenant match; approve first; SETTLED only after approve."""
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

    pay_shop = await resolve_payment_shop_owner_id(session, payment)
    if not _shop_ids_equal(pay_shop, settlement.shop_owner_id):
        settlement.status = SettlementStatus.FAILED.value
        settlement.error_message = "shop ownership mismatch"
        await session.commit()
        raise ValueError("ناسازگاری محدوده فروشگاه")

    # Already settled → repair pending payment if needed (never leave SETTLED+PENDING).
    if settlement.status == SettlementStatus.SETTLED.value:
        if payment.status == PaymentStatus.APPROVED.value:
            return payment
        if payment.status == PaymentStatus.PENDING.value:
            if not payment.receipt_file_id or str(payment.receipt_file_id).startswith(
                "card_auto:awaiting"
            ):
                ref = external_ref or settlement.external_ref or str(settlement.id)
                payment.receipt_file_id = f"{settlement.channel}:{settlement.provider}:{ref}"[:255]
            await approve_payment(session, payment, reviewer_tg=reviewer_tg)
            await session.refresh(payment)
            return payment
        raise ValueError("وضعیت پرداخت برای تسویه مناسب نیست")

    settlement, won = await _claim_for_settle(session, settlement, external_ref=external_ref)
    if not won:
        return await _wait_for_peer_settle(session, settlement, payment)

    if payment.status == PaymentStatus.APPROVED.value:
        await _finalize_settled(session, settlement)
        await session.commit()
        return payment

    if payment.status != PaymentStatus.PENDING.value:
        await _revert_claim_to_awaiting(session, settlement, error="payment not pending")
        await session.commit()
        raise ValueError("وضعیت پرداخت برای تسویه مناسب نیست")

    if not payment.receipt_file_id or str(payment.receipt_file_id).startswith("card_auto:awaiting"):
        ref = external_ref or settlement.external_ref or str(settlement.id)
        payment.receipt_file_id = f"{settlement.channel}:{settlement.provider}:{ref}"[:255]

    try:
        await approve_payment(session, payment, reviewer_tg=reviewer_tg)
    except ValueError as exc:
        if "قبلاً تأیید شده" in str(exc):
            await _finalize_settled(session, settlement)
            await session.commit()
            await session.refresh(payment)
            return payment
        await _revert_claim_to_awaiting(session, settlement, error=str(exc))
        await session.commit()
        raise
    except Exception as exc:
        await _revert_claim_to_awaiting(session, settlement, error=str(exc))
        await session.commit()
        raise

    await _finalize_settled(session, settlement)
    await session.commit()
    await session.refresh(payment)
    await session.refresh(settlement)
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

    payment = await session.get(Payment, int(settlement.payment_id))
    if not payment:
        raise ValueError("پرداخت یافت نشد")
    if int(payment.amount) != int(settlement.amount):
        raise ValueError("مبلغ پرداخت با تسویه هم‌خوانی ندارد")

    if settlement.status == SettlementStatus.SETTLED.value:
        # Repair path if needed.
        await settle_and_approve(
            session,
            settlement,
            expected_amount=int(settlement.amount),
            external_ref=settlement.external_ref,
            reviewer_tg=0,
        )
        await session.refresh(settlement)
        return settlement

    if provider == "mock":
        # Token required while still open; settling/settled already consumed it.
        if settlement.status in {
            SettlementStatus.CREATED.value,
            SettlementStatus.AWAITING.value,
        }:
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
    if settlement.external_ref and str(settlement.external_ref).lower() != str(external_ref).lower():
        raise ValueError("شناسه تراکنش با تسویه هم‌خوانی ندارد")

    # Real PSP: callback alone is never enough — adapter.verify talks to provider.
    verified = await adapter.verify(
        external_ref=external_ref,
        amount=int(settlement.amount),
        callback_params=callback_params,
    )
    if not verified.ok:
        # Soft cancel (Status=NOK / user backed out) must NOT burn the settlement.
        # Anyone can hit the public return URL with Status=NOK and otherwise
        # permanently FAIL a pending checkout before the real payer finishes.
        cb_status = str(
            callback_params.get("Status") or callback_params.get("status") or ""
        ).strip().upper()
        if cb_status and cb_status != "OK":
            raise ValueError(verified.message or "پرداخت توسط کاربر تکمیل نشد")
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
    ``payment_id`` is required (no amount-only / cross-tenant matching).
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
    tkey = tenant_key_for(shop_owner_id)

    # Idempotent: same tenant+provider+external_ref already settling/settled.
    existing = (
        await session.execute(
            select(PaymentSettlement).where(
                PaymentSettlement.channel == CHANNEL_CARD_AUTO,
                PaymentSettlement.provider == provider,
                PaymentSettlement.tenant_key == tkey,
                PaymentSettlement.external_ref == event.external_ref,
                PaymentSettlement.status.in_(
                    (
                        SettlementStatus.SETTLING.value,
                        SettlementStatus.SETTLED.value,
                    )
                ),
            )
        )
    ).scalar_one_or_none()
    if existing:
        if existing.status == SettlementStatus.SETTLED.value:
            return existing
        # Concurrent settling — wait path: finish approve if ours.
        return await settle_and_approve(
            session,
            existing,
            expected_amount=int(existing.amount),
            external_ref=event.external_ref,
            reviewer_tg=0,
        )

    payment = await session.get(Payment, int(event.payment_id))
    if not payment:
        raise ValueError("پرداخت یافت نشد")
    await assert_payment_in_shop(session, payment, shop_owner_id=shop_owner_id)

    if payment.status == PaymentStatus.APPROVED.value:
        # Already paid — return settled row if any.
        settled = await _get_by_idem(session, idem_key_card_auto(int(payment.id)))
        if settled and settled.status == SettlementStatus.SETTLED.value:
            return settled
        raise ValueError("پرداخت قبلاً تأیید شده")

    if payment.status != PaymentStatus.PENDING.value:
        raise ValueError("پرداخت در وضعیت مناسب نیست")
    if int(payment.amount) != int(event.amount):
        raise ValueError("مبلغ با پرداخت هم‌خوانی ندارد")

    settlement = await _get_by_idem(session, idem_key_card_auto(int(payment.id)))
    if settlement is None:
        settlement = await _get_open_for_payment_channel(
            session, payment_id=int(payment.id), channel=CHANNEL_CARD_AUTO
        )

    if settlement is None:
        candidate = PaymentSettlement(
            payment_id=int(payment.id),
            shop_owner_id=shop_owner_id,
            tenant_key=tkey,
            channel=CHANNEL_CARD_AUTO,
            provider=provider,
            status=SettlementStatus.AWAITING.value,
            amount=int(payment.amount),
            currency="IRT",
            idempotency_key=idem_key_card_auto(int(payment.id)),
        )
        inserted = await _insert_settlement_race_safe(session, candidate)
        settlement = inserted
    elif not _shop_ids_equal(settlement.shop_owner_id, shop_owner_id):
        raise ValueError("محدوده فروشگاه ناسازگار است")
    else:
        # Keep tenant_key aligned with path-derived shop (heal draft rows).
        if settlement.tenant_key != tkey:
            settlement.tenant_key = tkey

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
    """Best-effort Telegram delivery after automated settle (never rolls back finance)."""
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
            # Do not re-raise into callers that might confuse with payment failure —
            # financial approve already committed.
            logger.exception("settlement notify delivery failed payment=%s", payment.id)
            return
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
