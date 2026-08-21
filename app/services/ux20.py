"""UX20 product helpers — action center, PG health, delivery queue, gifts, funnel, etc."""

from __future__ import annotations

import json
import logging
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    BotUser,
    ChargeCode,
    DeliveryFailure,
    FunnelEvent,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    Plan,
    Ticket,
    UserService,
)

logger = logging.getLogger(__name__)

FUNNEL_STEPS = (
    "shop_open",
    "plan_view",
    "pay_start",
    "receipt",
    "delivered",
)

RISK_FLAG_LABELS = {
    "multi_trial": "چند تست",
    "repeat_reject": "رد مکرر",
    "many_tickets": "تیکت زیاد",
    "manual": "دستی",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_charge_code(raw: str) -> str:
    return re.sub(r"\s+", "", (raw or "").strip()).upper()


def generate_charge_code(prefix: str = "GIFT") -> str:
    alphabet = string.ascii_uppercase + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{normalize_charge_code(prefix) or 'GIFT'}-{body}"


def parse_risk_flags(raw: str | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for part in str(raw).replace(";", ",").split(","):
        key = part.strip().lower()
        if key and key not in out:
            out.append(key)
    return out


def serialize_risk_flags(flags: list[str] | None) -> str | None:
    cleaned = parse_risk_flags(",".join(flags or []))
    return ",".join(cleaned) if cleaned else None


def risk_badge_label(flags: list[str] | None) -> str | None:
    if not flags:
        return None
    labels = [RISK_FLAG_LABELS.get(f, f) for f in flags]
    return " · ".join(labels)


async def resolve_pg_open_url(session: AsyncSession, *, is_admin: bool) -> str:
    """External PasarGuard dashboard URL for quick-open button."""
    from app.config import get_settings, normalize_pg_base_url
    from app.services.resellers import get_reseller_pg_panel_base_url

    if is_admin:
        return normalize_pg_base_url(get_settings().pg_base_url or "")
    return await get_reseller_pg_panel_base_url(session)


async def check_pg_connection(*, reseller_user_id: int | None = None, session: AsyncSession | None = None) -> dict[str, Any]:
    """Lightweight PasarGuard reachability probe."""
    try:
        if reseller_user_id and session is not None:
            from app.services.pasarguard import get_pg_for_reseller

            pg = await get_pg_for_reseller(session, int(reseller_user_id))
        else:
            from app.services.pasarguard import get_pg

            pg = get_pg()
        await pg.ensure_token()
        stats = None
        try:
            stats = await pg.get_system_stats()
        except Exception:
            stats = None
        version = None
        if isinstance(stats, dict):
            version = stats.get("version")
        return {
            "ok": True,
            "error": None,
            "version": str(version) if version else None,
            "base_url": getattr(pg, "base_url", None),
        }
    except Exception:
        return {
            "ok": False,
            "error": "اتصال به پاسارگارد برقرار نشد",
            "version": None,
            "base_url": None,
        }


async def build_action_center(
    session: AsyncSession,
    *,
    reseller_id: int | None = None,
    expire_days: int = 3,
) -> dict[str, Any]:
    """Daily ops shortcuts: receipts, tickets, failed deliveries, expiring soon."""
    expire_days = max(1, min(30, int(expire_days or 3)))

    pending_q = (
        select(func.count())
        .select_from(Payment)
        .outerjoin(Order, Order.id == Payment.order_id)
        .where(
            Payment.status == PaymentStatus.PENDING.value,
            Payment.receipt_file_id.is_not(None),
        )
    )
    tickets_q = select(func.count()).select_from(Ticket).where(Ticket.status == "open")
    fail_q = (
        select(func.count())
        .select_from(DeliveryFailure)
        .where(DeliveryFailure.resolved_at.is_(None))
    )

    if reseller_id is None:
        pending_q = pending_q.where(
            or_(Payment.is_wallet_topup.is_(True), Order.reseller_id.is_(None))
        )
        tickets_q = tickets_q.join(BotUser, BotUser.id == Ticket.user_id).where(
            BotUser.reseller_id.is_(None)
        )
        fail_q = fail_q.where(DeliveryFailure.reseller_id.is_(None))
    else:
        rid = int(reseller_id)
        pending_q = pending_q.join(BotUser, BotUser.id == Payment.user_id).where(
            BotUser.reseller_id == rid
        )
        tickets_q = tickets_q.join(BotUser, BotUser.id == Ticket.user_id).where(
            BotUser.reseller_id == rid
        )
        fail_q = fail_q.where(DeliveryFailure.reseller_id == rid)

    pending = int((await session.execute(pending_q)).scalar() or 0)
    tickets = int((await session.execute(tickets_q)).scalar() or 0)
    failures = int((await session.execute(fail_q)).scalar() or 0)

    # Expiring: only scan services that could expire in-window (created within
    # max plan length), instead of loading the full service table.
    cutoff = _utcnow() + timedelta(days=expire_days)
    now = _utcnow()
    max_days = int(
        (
            await session.execute(
                select(func.coalesce(func.max(Plan.duration_days), 0)).select_from(Plan)
            )
        ).scalar()
        or 0
    )
    expiring = 0
    if max_days > 0:
        scan_since = now - timedelta(days=max_days)
        rows = (
            await session.execute(
                select(UserService.created_at, Plan.duration_days)
                .select_from(UserService)
                .join(Plan, Plan.id == UserService.plan_id)
                .join(BotUser, BotUser.id == UserService.bot_user_id)
                .where(
                    UserService.plan_id.is_not(None),
                    Plan.duration_days.is_not(None),
                    UserService.created_at.is_not(None),
                    UserService.created_at >= scan_since,
                    BotUser.reseller_id.is_(None)
                    if reseller_id is None
                    else BotUser.reseller_id == int(reseller_id),
                )
            )
        ).all()
        for created, days in rows:
            if not created or not days:
                continue
            try:
                exp = created
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                exp = exp + timedelta(days=int(days))
            except Exception:
                continue
            if now <= exp <= cutoff:
                expiring += 1

    items: list[dict[str, Any]] = []
    if pending:
        items.append(
            {
                "key": "pending",
                "title": f"{pending} رسید در انتظار",
                "detail": "تأیید یا رد پرداخت‌ها",
                "href": "/finance?tab=payments",
                "tone": "warn",
            }
        )
    if failures:
        items.append(
            {
                "key": "delivery",
                "title": f"{failures} تحویل ناموفق",
                "detail": "صف تلاش مجدد",
                "href": "/finance?tab=delivery",
                "tone": "err",
            }
        )
    if tickets:
        items.append(
            {
                "key": "tickets",
                "title": f"{tickets} تیکت باز",
                "detail": "پشتیبانی کاربران",
                "href": "/tickets",
                "tone": "warn",
            }
        )
    if expiring:
        items.append(
            {
                "key": "expiring",
                "title": f"{expiring} سرویس نزدیک انقضا",
                "detail": f"تا {expire_days} روز آینده",
                "href": "/users",
                "tone": "neutral",
            }
        )

    return {
        "pending": pending,
        "tickets": tickets,
        "failures": failures,
        "expiring": expiring,
        # Key must NOT be named ``items`` — Jinja ``ac.items`` resolves to dict.items().
        "entries": items,
        "has_items": bool(items),
    }


async def record_delivery_failure(
    session: AsyncSession,
    *,
    order: Order,
    error: str,
    payment_id: int | None = None,
) -> DeliveryFailure:
    existing = (
        await session.execute(
            select(DeliveryFailure)
            .where(
                DeliveryFailure.order_id == int(order.id),
                DeliveryFailure.resolved_at.is_(None),
            )
            .order_by(DeliveryFailure.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    msg = (error or "")[:2000]
    now = _utcnow()
    if existing:
        existing.error = msg
        existing.attempts = int(existing.attempts or 0) + 1
        existing.last_attempt_at = now
        if payment_id:
            existing.payment_id = int(payment_id)
        await session.flush()
        return existing
    row = DeliveryFailure(
        order_id=int(order.id),
        payment_id=int(payment_id) if payment_id else None,
        reseller_id=int(order.reseller_id) if order.reseller_id else None,
        error=msg,
        attempts=1,
        last_attempt_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def note_delivery_send_failure(
    session: AsyncSession,
    *,
    order: Order | None,
    error: str,
    payment: Payment | None = None,
) -> None:
    """After approve: record DeliveryFailure and stamp payment.review_note."""
    if order is None:
        return
    try:
        await record_delivery_failure(
            session,
            order=order,
            error=error,
            payment_id=int(payment.id) if payment is not None else None,
        )
        if payment is not None:
            payment.review_note = payment.review_note or "delivery_failed"
        await session.commit()
    except Exception:
        logger.debug("note_delivery_send_failure failed", exc_info=True)


async def resolve_delivery_failure(session: AsyncSession, order_id: int) -> None:
    now = _utcnow()
    await session.execute(
        update(DeliveryFailure)
        .where(
            DeliveryFailure.order_id == int(order_id),
            DeliveryFailure.resolved_at.is_(None),
        )
        .values(resolved_at=now)
    )


async def list_open_delivery_failures(
    session: AsyncSession, *, reseller_id: int | None = None, limit: int = 100
) -> list[DeliveryFailure]:
    q = (
        select(DeliveryFailure)
        .where(DeliveryFailure.resolved_at.is_(None))
        .order_by(DeliveryFailure.last_attempt_at.desc())
        .limit(limit)
    )
    if reseller_id is None:
        q = q.where(DeliveryFailure.reseller_id.is_(None))
    else:
        q = q.where(DeliveryFailure.reseller_id == int(reseller_id))
    return list((await session.execute(q)).scalars().all())


async def retry_delivery(session: AsyncSession, order_id: int) -> Order:
    from app.services.delivery import send_delivery_to_user
    from app.services.orders import deliver_order

    order = (
        await session.execute(
            select(Order)
            .where(Order.id == int(order_id))
            .options(selectinload(Order.plan), selectinload(Order.user))
        )
    ).scalar_one_or_none()
    if not order:
        raise ValueError("سفارش پیدا نشد")
    try:
        if order.status == OrderStatus.DELIVERED.value and order.service_id:
            # Resend Telegram delivery only
            await send_delivery_to_user(session, order)
        elif order.status in {
            OrderStatus.PAID.value,
            OrderStatus.DELIVERING.value,
            OrderStatus.AWAITING_APPROVAL.value,
        }:
            if order.status != OrderStatus.PAID.value:
                order.status = OrderStatus.PAID.value
                await session.commit()
            order = await deliver_order(session, order)
            try:
                await send_delivery_to_user(session, order)
            except Exception as send_exc:
                await record_delivery_failure(session, order=order, error=str(send_exc))
                await session.commit()
                raise
        else:
            raise ValueError("این سفارش برای تلاش مجدد آماده نیست")
        await resolve_delivery_failure(session, int(order.id))
        await session.commit()
        return order
    except Exception as exc:
        await record_delivery_failure(session, order=order, error=str(exc))
        await session.commit()
        raise


async def clone_plan(session: AsyncSession, plan_id: int, *, owner_reseller_id: int | None) -> Plan:
    src = (
        await session.execute(select(Plan).where(Plan.id == int(plan_id)))
    ).scalar_one_or_none()
    if not src:
        raise ValueError("پلن پیدا نشد")
    if owner_reseller_id is None:
        if src.owner_reseller_id is not None:
            raise ValueError("دسترسی ندارید")
    else:
        if int(src.owner_reseller_id or 0) != int(owner_reseller_id):
            raise ValueError("دسترسی ندارید")
    copy = Plan(
        name=f"{src.name} (کپی)",
        description=src.description,
        price=int(src.price or 0),
        duration_days=int(src.duration_days or 30),
        data_limit_gb=src.data_limit_gb,
        pg_template_id=src.pg_template_id,
        pg_group_ids=src.pg_group_ids,
        pg_username_prefix=src.pg_username_prefix,
        pg_username_suffix=src.pg_username_suffix,
        pg_username_pattern=src.pg_username_pattern,
        owner_reseller_id=src.owner_reseller_id,
        is_active=False,
        is_trial=bool(src.is_trial),
        sort_order=int(src.sort_order or 0),
    )
    session.add(copy)
    await session.commit()
    await session.refresh(copy)
    return copy


async def redeem_charge_code(
    session: AsyncSession,
    *,
    user: BotUser,
    code: str,
) -> tuple[ChargeCode, int]:
    """Credit wallet from a gift/charge code. Returns (code_row, new_balance)."""
    key = normalize_charge_code(code)
    if not key:
        raise ValueError("کد نامعتبر است")
    row = (
        await session.execute(select(ChargeCode).where(ChargeCode.code == key))
    ).scalar_one_or_none()
    if not row or not row.is_active:
        raise ValueError("کد نامعتبر یا غیرفعال است")
    # Shop scoping: platform codes (reseller_id NULL) for platform users;
    # shop codes only for that shop's customers.
    user_rid = int(user.reseller_id) if user.reseller_id else None
    code_rid = int(row.reseller_id) if row.reseller_id else None
    if code_rid != user_rid:
        raise ValueError("این کد برای فروشگاه شما نیست")
    if row.max_uses is not None and int(row.used_count or 0) >= int(row.max_uses):
        raise ValueError("سقف استفاده از کد پر شده")
    amount = int(row.amount or 0)
    if amount <= 0:
        raise ValueError("مبلغ کد نامعتبر است")
    # Atomic consume
    claim = await session.execute(
        update(ChargeCode)
        .where(
            ChargeCode.id == row.id,
            ChargeCode.is_active.is_(True),
            or_(ChargeCode.max_uses.is_(None), ChargeCode.used_count < ChargeCode.max_uses),
        )
        .values(used_count=ChargeCode.used_count + 1)
        .execution_options(synchronize_session=False)
    )
    if claim.rowcount != 1:
        raise ValueError("کد قابل استفاده نیست")
    user.wallet_balance = int(user.wallet_balance or 0) + amount
    await session.flush()
    await session.refresh(row)
    return row, int(user.wallet_balance)


async def create_charge_code(
    session: AsyncSession,
    *,
    amount: int,
    max_uses: int | None = 1,
    reseller_id: int | None = None,
    note: str | None = None,
    code: str | None = None,
) -> ChargeCode:
    amount = int(amount)
    if amount <= 0:
        raise ValueError("مبلغ باید بزرگ‌تر از صفر باشد")
    raw = normalize_charge_code(code) if code else generate_charge_code()
    if not raw:
        raise ValueError("کد نامعتبر است")
    exists = (
        await session.execute(select(ChargeCode.id).where(ChargeCode.code == raw))
    ).scalar_one_or_none()
    if exists:
        raise ValueError("این کد از قبل وجود دارد")
    row = ChargeCode(
        code=raw,
        amount=amount,
        max_uses=int(max_uses) if max_uses is not None else None,
        used_count=0,
        is_active=True,
        reseller_id=int(reseller_id) if reseller_id else None,
        note=(note or "").strip()[:255] or None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def record_funnel_event(
    session: AsyncSession,
    *,
    step: str,
    user_id: int | None = None,
    reseller_id: int | None = None,
    plan_id: int | None = None,
    order_id: int | None = None,
    idempotency_key: str | None = None,
) -> None:
    step = (step or "").strip()
    if step not in FUNNEL_STEPS:
        return
    key = (idempotency_key or "").strip()
    if not key:
        key = f"{step}:{user_id or 0}:{plan_id or 0}:{order_id or 0}:{int(_utcnow().timestamp())}"
    existing = (
        await session.execute(select(FunnelEvent.id).where(FunnelEvent.idempotency_key == key))
    ).scalar_one_or_none()
    if existing:
        return
    session.add(
        FunnelEvent(
            step=step,
            user_id=int(user_id) if user_id else None,
            reseller_id=int(reseller_id) if reseller_id else None,
            plan_id=int(plan_id) if plan_id else None,
            order_id=int(order_id) if order_id else None,
            idempotency_key=key[:128],
        )
    )
    try:
        await session.flush()
    except Exception:
        await session.rollback()


async def funnel_summary(
    session: AsyncSession, *, reseller_id: int | None = None, days: int = 7
) -> dict[str, int]:
    """Step counts for the behavior panel (7d default)."""
    since = _utcnow() - timedelta(days=max(1, min(90, days)))
    q = select(FunnelEvent.step, func.count()).where(FunnelEvent.created_at >= since)
    if reseller_id is None:
        q = q.where(FunnelEvent.reseller_id.is_(None))
    else:
        q = q.where(FunnelEvent.reseller_id == int(reseller_id))
    q = q.group_by(FunnelEvent.step)
    rows = (await session.execute(q)).all()
    out: dict[str, int] = {s: 0 for s in FUNNEL_STEPS}
    for step, cnt in rows:
        if step in out:
            out[step] = int(cnt or 0)
    # Fallback derive from orders when funnel empty
    if not any(out.values()):
        oq = select(Order.status, func.count()).where(Order.created_at >= since)
        if reseller_id is None:
            oq = oq.where(Order.reseller_id.is_(None))
        else:
            oq = oq.where(Order.reseller_id == int(reseller_id))
        oq = oq.group_by(Order.status)
        for st, cnt in (await session.execute(oq)).all():
            n = int(cnt or 0)
            if st in {
                OrderStatus.PENDING.value,
                OrderStatus.AWAITING_RECEIPT.value,
                OrderStatus.AWAITING_APPROVAL.value,
                OrderStatus.PAID.value,
                OrderStatus.DELIVERING.value,
                OrderStatus.DELIVERED.value,
            }:
                out["pay_start"] += n
            if st in {
                OrderStatus.AWAITING_APPROVAL.value,
                OrderStatus.PAID.value,
                OrderStatus.DELIVERING.value,
                OrderStatus.DELIVERED.value,
            }:
                out["receipt"] += n
            if st == OrderStatus.DELIVERED.value:
                out["delivered"] += n
    return out


async def suggest_receipt_matches(
    session: AsyncSession,
    *,
    payment: Payment,
    window_minutes: int = 120,
    reseller_id: int | None = None,
) -> list[dict[str, Any]]:
    """Soft-match other pending payments with same amount in time window.

    Tenant-scoped: a reseller (``reseller_id`` set) must only ever see matches
    that belong to their own shop (order tenant or payer's shop membership).
    Platform scope (``reseller_id is None``) only sees platform-level payments.
    """
    window_minutes = max(5, min(24 * 60, int(window_minutes or 120)))
    created = payment.created_at or _utcnow()
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    lo = created - timedelta(minutes=window_minutes)
    hi = created + timedelta(minutes=window_minutes)
    q = (
        select(Payment)
        .join(BotUser, BotUser.id == Payment.user_id)
        .options(selectinload(Payment.order))
        .where(
            Payment.id != int(payment.id),
            Payment.status == PaymentStatus.PENDING.value,
            Payment.amount == int(payment.amount or 0),
            Payment.created_at >= lo,
            Payment.created_at <= hi,
        )
        .order_by(Payment.created_at.desc())
    )
    if reseller_id is None:
        # Platform scope: only payers with no shop membership at all.
        q = q.where(BotUser.reseller_id.is_(None))
    else:
        rid = int(reseller_id)
        q = q.join(Order, Order.id == Payment.order_id, isouter=True).where(
            or_(
                and_(Payment.is_wallet_topup.is_(True), BotUser.reseller_id == rid),
                and_(Payment.is_wallet_topup.is_(False), Order.reseller_id == rid),
            )
        )
    rows = list((await session.execute(q.limit(5))).scalars().all())
    out = []
    for p in rows:
        out.append(
            {
                "id": p.id,
                "order_id": p.order_id,
                "amount": p.amount,
                "user_id": p.user_id,
                "created_at": p.created_at,
            }
        )
    return out


def compute_user_risk_flags(
    *,
    trial_count: int = 0,
    rejected_payments: int = 0,
    open_tickets: int = 0,
    existing: list[str] | None = None,
) -> list[str]:
    flags = list(existing or [])
    if trial_count >= 2 and "multi_trial" not in flags:
        flags.append("multi_trial")
    if rejected_payments >= 3 and "repeat_reject" not in flags:
        flags.append("repeat_reject")
    if open_tickets >= 3 and "many_tickets" not in flags:
        flags.append("many_tickets")
    return flags


async def refresh_user_risk(session: AsyncSession, user: BotUser) -> list[str]:
    from app.db.models import Order as Ord

    trial_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Ord)
                .join(Plan, Plan.id == Ord.plan_id)
                .where(Ord.user_id == user.id, Plan.is_trial.is_(True))
            )
        ).scalar()
        or 0
    )
    rejected = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Payment)
                .where(
                    Payment.user_id == user.id,
                    Payment.status == PaymentStatus.REJECTED.value,
                )
            )
        ).scalar()
        or 0
    )
    tickets = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Ticket)
                .where(Ticket.user_id == user.id, Ticket.status == "open")
            )
        ).scalar()
        or 0
    )
    existing = [f for f in parse_risk_flags(user.risk_flags) if f == "manual"]
    flags = compute_user_risk_flags(
        trial_count=trial_count,
        rejected_payments=rejected,
        open_tickets=tickets,
        existing=existing,
    )
    user.risk_flags = serialize_risk_flags(flags)
    await session.flush()
    return flags


def bot_deep_link(bot_username: str | None, payload: str) -> str | None:
    uname = (bot_username or "").strip().lstrip("@")
    if not uname:
        return None
    payload = (payload or "").strip()
    if not payload:
        return f"https://t.me/{uname}"
    return f"https://t.me/{uname}?start={quote(payload)}"


async def build_magic_links_context(session: AsyncSession, staff: dict) -> dict[str, Any]:
    """Username + deep links for settings «لینک‌های سریع» tab."""
    from app.config import get_settings
    from app.db.models import ResellerProfile
    from app.services.home_overview import check_bot_connection
    from app.services.shop_scope import is_platform_admin, shop_owner_id

    rid = None if is_platform_admin(staff) else shop_owner_id(staff)
    bot_username = None
    if rid:
        profile = (
            await session.execute(
                select(ResellerProfile).where(ResellerProfile.user_id == int(rid))
            )
        ).scalar_one_or_none()
        bot_username = (profile.bot_username if profile else None) or None
        if not bot_username and profile and profile.bot_token:
            st = await check_bot_connection(profile.bot_token)
            bot_username = st.get("username")
    else:
        st = await check_bot_connection(get_settings().bot_token)
        bot_username = st.get("username")
    links = {
        "renew": bot_deep_link(bot_username, "renew"),
        "wallet": bot_deep_link(bot_username, "wallet"),
        "support": bot_deep_link(bot_username, "support"),
        "config": bot_deep_link(bot_username, "config"),
        "gift": bot_deep_link(bot_username, "gift"),
    }
    return {"bot_username": bot_username, "links": links}


async def export_shop_bundle(
    session: AsyncSession, *, reseller_id: int | None = None
) -> dict[str, Any]:
    from app.services.users import get_all_settings

    values = await get_all_settings(session, reseller_id=reseller_id)
    # Keep operator-facing keys; drop secrets-ish if any sneak in
    skip = {"bot_token", "webhook_secret"}
    settings = {k: v for k, v in values.items() if k not in skip}
    pq = select(Plan).order_by(Plan.sort_order.asc(), Plan.id.asc())
    if reseller_id is None:
        pq = pq.where(Plan.owner_reseller_id.is_(None))
    else:
        pq = pq.where(Plan.owner_reseller_id == int(reseller_id))
    plans = []
    for p in (await session.execute(pq)).scalars().all():
        plans.append(
            {
                "name": p.name,
                "description": p.description,
                "price": p.price,
                "duration_days": p.duration_days,
                "data_limit_gb": p.data_limit_gb,
                "pg_template_id": p.pg_template_id,
                "pg_group_ids": p.pg_group_ids,
                "pg_username_prefix": p.pg_username_prefix,
                "pg_username_suffix": p.pg_username_suffix,
                "pg_username_pattern": p.pg_username_pattern,
                "is_active": bool(p.is_active),
                "is_trial": bool(p.is_trial),
                "sort_order": p.sort_order,
            }
        )
    return {
        "format": "pgclock-shop-bundle",
        "version": 1,
        "exported_at": _utcnow().isoformat(),
        "reseller_id": reseller_id,
        "settings": settings,
        "plans": plans,
    }


async def import_shop_bundle(
    session: AsyncSession,
    payload: dict[str, Any],
    *,
    reseller_id: int | None = None,
    replace_plans: bool = False,
) -> dict[str, int]:
    from app.services.users import set_settings_bulk

    if not isinstance(payload, dict) or payload.get("format") != "pgclock-shop-bundle":
        raise ValueError("فرمت فایل نامعتبر است")
    settings = payload.get("settings") or {}
    if not isinstance(settings, dict):
        raise ValueError("settings نامعتبر است")
    # Only known keys
    from app.services.users import DEFAULT_SETTINGS

    clean = {
        str(k): "" if v is None else str(v)
        for k, v in settings.items()
        if str(k) in DEFAULT_SETTINGS
    }
    if clean:
        await set_settings_bulk(session, clean, reseller_id=reseller_id)
    plans_in = payload.get("plans") or []
    created = 0
    if replace_plans and isinstance(plans_in, list):
        q = select(Plan)
        if reseller_id is None:
            q = q.where(Plan.owner_reseller_id.is_(None), Plan.is_trial.is_(False))
        else:
            q = q.where(Plan.owner_reseller_id == int(reseller_id), Plan.is_trial.is_(False))
        for old in (await session.execute(q)).scalars().all():
            await session.delete(old)
        await session.flush()
    if isinstance(plans_in, list):
        for raw in plans_in:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            session.add(
                Plan(
                    name=name[:128],
                    description=(str(raw.get("description") or "")[:2000] or None),
                    price=int(raw.get("price") or 0),
                    duration_days=int(raw.get("duration_days") or 30),
                    data_limit_gb=raw.get("data_limit_gb"),
                    pg_template_id=raw.get("pg_template_id"),
                    pg_group_ids=raw.get("pg_group_ids"),
                    pg_username_prefix=raw.get("pg_username_prefix"),
                    pg_username_suffix=raw.get("pg_username_suffix"),
                    pg_username_pattern=raw.get("pg_username_pattern"),
                    owner_reseller_id=int(reseller_id) if reseller_id else None,
                    is_active=bool(raw.get("is_active", True)),
                    is_trial=False,
                    sort_order=int(raw.get("sort_order") or 0),
                )
            )
            created += 1
    await session.commit()
    return {"settings": len(clean), "plans": created}


def capacity_used_pct(meter: dict | None) -> float | None:
    if not meter:
        return None
    pct = meter.get("pct")
    try:
        return float(pct) if pct is not None else None
    except Exception:
        return None


def capacity_should_warn(meters: list[dict | None], threshold: float = 80.0) -> bool:
    for m in meters:
        pct = capacity_used_pct(m)
        if pct is not None and pct >= threshold:
            return True
    return False


async def maybe_warn_reseller_capacity(
    session: AsyncSession,
    profile,
    pg_limits: dict | None,
    *,
    threshold: float | None = None,
) -> bool:
    """
    If any PG meter is at/above capacity_warn_pct and we have not warned yet,
    stamp capacity_warned_at (once). Returns True when a new warn was recorded.
    """
    if not profile or not pg_limits or not pg_limits.get("ready"):
        return False
    if getattr(profile, "capacity_warned_at", None) is not None:
        return False
    if threshold is None:
        from app.services.users import get_setting

        try:
            threshold = float(await get_setting(session, "capacity_warn_pct", "80") or 80)
        except Exception:
            threshold = 80.0
    meters = [pg_limits.get("users"), pg_limits.get("traffic")]
    if not capacity_should_warn(meters, float(threshold)):
        return False
    profile.capacity_warned_at = _utcnow()
    try:
        await session.commit()
    except Exception:
        logger.debug("capacity_warned_at commit failed", exc_info=True)
        return False
    # Best-effort Telegram nudge to shop owner (optional)
    try:
        from app.db.models import BotUser
        from app.services.reseller_bots import open_notify_bot_for_reseller

        owner = await session.get(BotUser, int(profile.user_id))
        if not owner:
            return True
        bot, should_close = await open_notify_bot_for_reseller(session, int(profile.user_id))
        if bot is None:
            return True
        try:
            hot = []
            for key, label in (("users", "کاربر"), ("traffic", "حجم")):
                m = pg_limits.get(key) or {}
                pct = capacity_used_pct(m)
                if pct is not None and pct >= float(threshold):
                    hot.append(f"{label}: {pct:.0f}٪")
            detail = "، ".join(hot) if hot else f"≥{threshold:.0f}٪"
            await bot.send_message(
                int(owner.telegram_id),
                f"⚠️ ظرفیت پنل پاسارگارد نزدیک پر شدن است ({detail}).\n"
                "از وب‌پنل → خانه وضعیت سهمیه را بررسی کنید.",
                parse_mode="HTML",
            )
        finally:
            if should_close:
                await bot.session.close()
    except Exception:
        logger.debug("capacity warn telegram failed", exc_info=True)
    return True


async def build_admin_daily_report(session: AsyncSession) -> str:
    """Backward-compatible Owner report (platform shop only)."""
    from app.services.daily_report import (
        ACTOR_OWNER,
        DEFAULT_REPORT_TEMPLATE,
        build_daily_report,
    )
    from app.services.users import get_setting

    template = await get_setting(session, "admin_daily_report_template", "")
    metrics = await get_setting(session, "admin_daily_report_metrics", "")
    return await build_daily_report(
        session,
        reseller_id=None,
        actor=ACTOR_OWNER,
        admin_name="مالک سیستم",
        template=template or DEFAULT_REPORT_TEMPLATE,
        metrics_raw=metrics,
    )


def shop_bundle_to_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
