"""Referral + Loyalty / Points engine.

Extends existing referral_code / referred_by_id / referral_bonus wallet credit.
Points ledger is the audit source of truth; BotUser.points_balance is a cache.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import Select, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BotUser,
    LoyaltyReward,
    LoyaltyTier,
    Order,
    Plan,
    PointsRule,
    PointsTransaction,
    ReferralEvent,
    RewardRedemption,
    UserService,
)

logger = logging.getLogger(__name__)

# Human-friendly Persian labels for admin UI (never expose raw keys as primary labels)
EVENT_LABELS: dict[str, str] = {
    "purchase": "خرید موفق",
    "first_purchase": "اولین خرید کاربر",
    "renewal": "تمدید موفق",
    "referral_signup": "ثبت‌نام با دعوت",
    "referral_first_purchase": "اولین خرید دعوت‌شده",
    "referral_purchase": "خرید دعوت‌شده",
    "referral_qualification": "واجد شرایط شدن دعوت",
}

REWARD_TYPE_LABELS: dict[str, str] = {
    "traffic_gb": "ترافیک (گیگ)",
    "time_days": "زمان (روز)",
    "wallet_credit": "اعتبار کیف پول",
    "discount_percent": "تخفیف درصدی",
}

TX_TYPE_LABELS: dict[str, str] = {
    "earn": "دریافت",
    "spend": "مصرف",
    "adjust": "تعدیل ادمین",
    "reverse": "برگشت",
    "redeem": "بازخرید جایزه",
}

DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "name": "خرید موفق (به‌ازای هر گیگ)",
        "event_key": "purchase",
        "amount_mode": "per_gb",
        "amount": 1,
        "enabled": True,
        "sort_order": 10,
    },
    {
        "name": "اولین خرید کاربر",
        "event_key": "first_purchase",
        "amount_mode": "fixed",
        "amount": 50,
        "enabled": True,
        "first_time_only": True,
        "sort_order": 20,
    },
    {
        "name": "تمدید موفق",
        "event_key": "renewal",
        "amount_mode": "fixed",
        "amount": 20,
        "enabled": True,
        "sort_order": 30,
    },
    {
        "name": "ثبت‌نام با دعوت",
        "event_key": "referral_signup",
        "amount_mode": "fixed",
        "amount": 0,
        "enabled": True,
        "sort_order": 40,
    },
    {
        "name": "اولین خرید دعوت‌شده",
        "event_key": "referral_first_purchase",
        "amount_mode": "fixed",
        "amount": 50,
        "enabled": True,
        "first_time_only": True,
        "sort_order": 50,
    },
    {
        "name": "خرید دعوت‌شده",
        "event_key": "referral_purchase",
        "amount_mode": "fixed",
        "amount": 10,
        "enabled": True,
        "sort_order": 60,
    },
]

DEFAULT_TIERS: list[dict[str, Any]] = [
    {"name": "برنز", "min_points": 0, "max_points": 999, "sort_order": 1, "multiplier_bps": 10000},
    {"name": "نقره", "min_points": 1000, "max_points": 4999, "sort_order": 2, "multiplier_bps": 10000},
    {"name": "طلا", "min_points": 5000, "max_points": None, "sort_order": 3, "multiplier_bps": 10000},
]

DEFAULT_REWARDS: list[dict[str, Any]] = [
    {
        "name": "۵ گیگ رایگان",
        "description": "افزودن ۵ گیگ به یکی از سرویس‌های فعال",
        "reward_type": "traffic_gb",
        "reward_value": 5,
        "points_cost": 100,
        "sort_order": 10,
    },
    {
        "name": "۱۰ گیگ رایگان",
        "description": "افزودن ۱۰ گیگ به یکی از سرویس‌های فعال",
        "reward_type": "traffic_gb",
        "reward_value": 10,
        "points_cost": 180,
        "sort_order": 20,
    },
    {
        "name": "۳۰ روز زمان",
        "description": "افزودن ۳۰ روز به یکی از سرویس‌های فعال",
        "reward_type": "time_days",
        "reward_value": 30,
        "points_cost": 250,
        "sort_order": 30,
    },
    {
        "name": "۵۰٬۰۰۰ اعتبار کیف پول",
        "description": "واریز اعتبار به کیف پول (غیرقابل برداشت نقدی)",
        "reward_type": "wallet_credit",
        "reward_value": 50000,
        "points_cost": 500,
        "sort_order": 40,
    },
]

SETTING_LOYALTY_ENABLED = "loyalty_enabled"
SETTING_POINTS_TO_WALLET_RATE = "points_to_wallet_rate"  # toman per 1 point when converting via wallet_credit rewards


@dataclass(frozen=True)
class TierInfo:
    name: str
    min_points: int
    max_points: int | None
    points_to_next: int | None
    multiplier_bps: int


async def ensure_loyalty_defaults(session: AsyncSession, *, reseller_id: int | None = None) -> None:
    """Seed default rules/tiers/rewards once (idempotent)."""
    from app.services.users import get_setting, set_setting

    enabled = await get_setting(session, SETTING_LOYALTY_ENABLED, "1", reseller_id=reseller_id)
    if enabled == "":
        await set_setting(session, SETTING_LOYALTY_ENABLED, "1", reseller_id=reseller_id)
    rate = await get_setting(session, SETTING_POINTS_TO_WALLET_RATE, "", reseller_id=reseller_id)
    if rate == "":
        await set_setting(session, SETTING_POINTS_TO_WALLET_RATE, "100", reseller_id=reseller_id)

    q: Select = select(func.count()).select_from(PointsRule)
    if reseller_id is None:
        q = q.where(PointsRule.reseller_id.is_(None))
    else:
        q = q.where(PointsRule.reseller_id == int(reseller_id))
    n = int((await session.execute(q)).scalar_one() or 0)
    if n == 0:
        for row in DEFAULT_RULES:
            session.add(
                PointsRule(
                    name=row["name"],
                    event_key=row["event_key"],
                    amount_mode=row["amount_mode"],
                    amount=int(row["amount"]),
                    enabled=bool(row.get("enabled", True)),
                    first_time_only=bool(row.get("first_time_only", False)),
                    sort_order=int(row.get("sort_order", 0)),
                    reseller_id=reseller_id,
                )
            )

    tn = int((await session.execute(select(func.count()).select_from(LoyaltyTier))).scalar_one() or 0)
    if tn == 0:
        for row in DEFAULT_TIERS:
            session.add(
                LoyaltyTier(
                    name=row["name"],
                    min_points=int(row["min_points"]),
                    max_points=row["max_points"],
                    sort_order=int(row["sort_order"]),
                    multiplier_bps=int(row["multiplier_bps"]),
                    enabled=True,
                )
            )

    rq: Select = select(func.count()).select_from(LoyaltyReward)
    if reseller_id is None:
        rq = rq.where(LoyaltyReward.reseller_id.is_(None))
    else:
        rq = rq.where(LoyaltyReward.reseller_id == int(reseller_id))
    rn = int((await session.execute(rq)).scalar_one() or 0)
    if rn == 0:
        for row in DEFAULT_REWARDS:
            session.add(
                LoyaltyReward(
                    name=row["name"],
                    description=row.get("description"),
                    reward_type=row["reward_type"],
                    reward_value=int(row["reward_value"]),
                    points_cost=int(row["points_cost"]),
                    enabled=True,
                    archived=False,
                    sort_order=int(row.get("sort_order", 0)),
                    reseller_id=reseller_id,
                )
            )
    await session.commit()


async def loyalty_enabled(session: AsyncSession, *, reseller_id: int | None = None) -> bool:
    from app.services.users import get_setting, on

    raw = await get_setting(session, SETTING_LOYALTY_ENABLED, "1", reseller_id=reseller_id)
    return on(raw)


def referral_link(bot_username: str, code: str) -> str:
    uname = (bot_username or "bot").lstrip("@")
    return f"https://t.me/{uname}?start=ref_{code}"


async def record_referral_event(
    session: AsyncSession,
    *,
    referrer_id: int,
    referred_id: int,
    event_key: str,
    source: str = "telegram",
    order_id: int | None = None,
    qualification_state: str = "pending",
    reward_state: str = "none",
    idempotency_key: str,
    meta: dict | None = None,
) -> ReferralEvent | None:
    if referrer_id == referred_id:
        return None
    existing = (
        await session.execute(
            select(ReferralEvent).where(ReferralEvent.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    ev = ReferralEvent(
        referrer_id=int(referrer_id),
        referred_id=int(referred_id),
        event_key=event_key,
        source=source,
        status="recorded",
        qualification_state=qualification_state,
        reward_state=reward_state,
        order_id=order_id,
        idempotency_key=idempotency_key,
        meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
    )
    session.add(ev)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return (
            await session.execute(
                select(ReferralEvent).where(ReferralEvent.idempotency_key == idempotency_key)
            )
        ).scalar_one_or_none()
    return ev


async def credit_points(
    session: AsyncSession,
    user: BotUser,
    amount: int,
    *,
    tx_type: str,
    source: str,
    reference: str | None,
    description: str,
    idempotency_key: str,
    meta: dict | None = None,
    created_by: str | None = None,
    commit: bool = True,
) -> PointsTransaction | None:
    """Credit points idempotently. Returns existing tx if idempotency_key already used."""
    if amount == 0:
        return None
    if amount < 0:
        raise ValueError("credit_points amount must be >= 0")
    existing = (
        await session.execute(
            select(PointsTransaction).where(PointsTransaction.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    with session.no_autoflush:
        result = await session.execute(
            update(BotUser)
            .where(BotUser.id == user.id)
            .values(points_balance=BotUser.points_balance + int(amount))
            .execution_options(synchronize_session=False)
        )
    if result.rowcount != 1:
        raise ValueError("کاربر یافت نشد")
    await session.refresh(user)
    tx = PointsTransaction(
        user_id=user.id,
        amount=int(amount),
        balance_after=int(user.points_balance),
        tx_type=tx_type,
        source=source,
        reference=reference,
        description=description,
        idempotency_key=idempotency_key,
        meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
        created_by=created_by,
    )
    session.add(tx)
    try:
        if commit:
            await session.commit()
            await session.refresh(user)
            await session.refresh(tx)
        else:
            await session.flush()
    except IntegrityError:
        await session.rollback()
        return (
            await session.execute(
                select(PointsTransaction).where(
                    PointsTransaction.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
    return tx


async def debit_points(
    session: AsyncSession,
    user: BotUser,
    amount: int,
    *,
    tx_type: str,
    source: str,
    reference: str | None,
    description: str,
    idempotency_key: str,
    meta: dict | None = None,
    created_by: str | None = None,
    commit: bool = True,
    allow_negative: bool = False,
) -> PointsTransaction | None:
    """Debit points. Prevents negative balance unless allow_negative (admin debt policy)."""
    if amount <= 0:
        raise ValueError("debit_points amount must be positive")
    existing = (
        await session.execute(
            select(PointsTransaction).where(PointsTransaction.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    cond = [BotUser.id == user.id]
    if not allow_negative:
        cond.append(BotUser.points_balance >= int(amount))
    with session.no_autoflush:
        result = await session.execute(
            update(BotUser)
            .where(*cond)
            .values(points_balance=BotUser.points_balance - int(amount))
            .execution_options(synchronize_session=False)
        )
    if result.rowcount != 1:
        raise ValueError("امتیاز کافی نیست")
    await session.refresh(user)
    tx = PointsTransaction(
        user_id=user.id,
        amount=-int(amount),
        balance_after=int(user.points_balance),
        tx_type=tx_type,
        source=source,
        reference=reference,
        description=description,
        idempotency_key=idempotency_key,
        meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
        created_by=created_by,
    )
    session.add(tx)
    try:
        if commit:
            await session.commit()
            await session.refresh(user)
            await session.refresh(tx)
        else:
            await session.flush()
    except IntegrityError:
        await session.rollback()
        return (
            await session.execute(
                select(PointsTransaction).where(
                    PointsTransaction.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
    return tx


async def reverse_points_tx(
    session: AsyncSession,
    original: PointsTransaction,
    *,
    reason: str,
    created_by: str | None = None,
    commit: bool = True,
) -> PointsTransaction | None:
    """Reverse a prior earn/spend. Idempotent via reverse:{original.id}."""
    key = f"reverse:{int(original.id)}"
    existing = (
        await session.execute(
            select(PointsTransaction).where(PointsTransaction.idempotency_key == key)
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    amt = int(original.amount)
    if amt == 0:
        return None
    user = await session.get(BotUser, original.user_id)
    if not user:
        return None
    if amt > 0:
        # Original was credit → debit back; allow negative (spent-points debt policy)
        return await debit_points(
            session,
            user,
            amt,
            tx_type="reverse",
            source=original.source,
            reference=original.reference,
            description=reason,
            idempotency_key=key,
            meta={"reversed_tx_id": original.id},
            created_by=created_by,
            commit=commit,
            allow_negative=True,
        )
    return await credit_points(
        session,
        user,
        -amt,
        tx_type="reverse",
        source=original.source,
        reference=original.reference,
        description=reason,
        idempotency_key=key,
        meta={"reversed_tx_id": original.id},
        created_by=created_by,
        commit=commit,
    )


async def admin_adjust_points(
    session: AsyncSession,
    user: BotUser,
    delta: int,
    *,
    reason: str,
    admin_identity: str,
) -> PointsTransaction:
    if not reason or not str(reason).strip():
        raise ValueError("دلیل الزامی است")
    if delta == 0:
        raise ValueError("مقدار نمی‌تواند صفر باشد")
    key = f"admin_adjust:{user.id}:{admin_identity}:{int(datetime.now(timezone.utc).timestamp())}:{delta}:{reason.strip()[:40]}"
    prev = int(user.points_balance or 0)
    if delta > 0:
        tx = await credit_points(
            session,
            user,
            delta,
            tx_type="adjust",
            source="admin",
            reference=None,
            description=reason.strip(),
            idempotency_key=key,
            meta={"previous_balance": prev},
            created_by=admin_identity,
            commit=True,
        )
    else:
        tx = await debit_points(
            session,
            user,
            -delta,
            tx_type="adjust",
            source="admin",
            reference=None,
            description=reason.strip(),
            idempotency_key=key,
            meta={"previous_balance": prev},
            created_by=admin_identity,
            commit=True,
            allow_negative=False,
        )
    if tx is None:
        raise ValueError("تعدیل انجام نشد")
    return tx


async def get_tier_for_points(session: AsyncSession, points: int) -> TierInfo:
    rows = list(
        (
            await session.execute(
                select(LoyaltyTier)
                .where(LoyaltyTier.enabled.is_(True))
                .order_by(LoyaltyTier.min_points.asc(), LoyaltyTier.sort_order.asc())
            )
        ).scalars().all()
    )
    if not rows:
        return TierInfo("برنز", 0, None, None, 10000)
    current = rows[0]
    for t in rows:
        if int(points) >= int(t.min_points):
            current = t
    nxt = None
    for t in rows:
        if int(t.min_points) > int(current.min_points):
            nxt = t
            break
    to_next = None
    if nxt is not None:
        to_next = max(0, int(nxt.min_points) - int(points))
    return TierInfo(
        name=current.name,
        min_points=int(current.min_points),
        max_points=int(current.max_points) if current.max_points is not None else None,
        points_to_next=to_next,
        multiplier_bps=int(current.multiplier_bps or 10000),
    )


def _plan_gb(plan: Plan | None) -> float:
    if not plan or plan.data_limit_gb is None:
        return 0.0
    try:
        return float(plan.data_limit_gb)
    except (TypeError, ValueError):
        return 0.0


async def _rules_for_event(
    session: AsyncSession,
    event_key: str,
    *,
    reseller_id: int | None,
) -> list[PointsRule]:
    q = (
        select(PointsRule)
        .where(
            PointsRule.event_key == event_key,
            PointsRule.enabled.is_(True),
        )
        .order_by(PointsRule.sort_order.asc(), PointsRule.id.asc())
    )
    if reseller_id is None:
        q = q.where(PointsRule.reseller_id.is_(None))
    else:
        q = q.where(PointsRule.reseller_id == int(reseller_id))
    rows = list((await session.execute(q)).scalars().all())
    if not rows and reseller_id is not None:
        # Fall back to platform rules
        q2 = (
            select(PointsRule)
            .where(
                PointsRule.event_key == event_key,
                PointsRule.enabled.is_(True),
                PointsRule.reseller_id.is_(None),
            )
            .order_by(PointsRule.sort_order.asc(), PointsRule.id.asc())
        )
        rows = list((await session.execute(q2)).scalars().all())
    return rows


async def _rule_passes(
    session: AsyncSession,
    rule: PointsRule,
    *,
    user: BotUser,
    order: Order | None,
    plan: Plan | None,
    gb: float,
) -> bool:
    if rule.plan_id and order and order.plan_id and int(rule.plan_id) != int(order.plan_id):
        return False
    if rule.plan_id and not order:
        return False
    amount = int(order.amount) if order else 0
    if int(rule.min_purchase_toman or 0) > 0 and amount < int(rule.min_purchase_toman):
        return False
    if int(rule.min_purchase_gb or 0) > 0 and gb < float(rule.min_purchase_gb):
        return False
    if int(rule.tier_min_points or 0) > 0 and int(user.points_balance or 0) < int(rule.tier_min_points):
        return False
    if rule.first_time_only:
        prior = (
            await session.execute(
                select(PointsTransaction.id)
                .where(
                    PointsTransaction.user_id == user.id,
                    PointsTransaction.source == f"rule:{rule.id}",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if prior is not None:
            return False
    if int(rule.cooldown_hours or 0) > 0:
        since = datetime.now(timezone.utc) - timedelta(hours=int(rule.cooldown_hours))
        recent = (
            await session.execute(
                select(PointsTransaction.id)
                .where(
                    PointsTransaction.user_id == user.id,
                    PointsTransaction.source == f"rule:{rule.id}",
                    PointsTransaction.created_at >= since,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if recent is not None:
            return False
    return True


def _compute_rule_amount(rule: PointsRule, *, gb: float, multiplier_bps: int) -> int:
    if rule.amount_mode == "per_gb":
        raw = int(rule.amount) * int(gb)
    else:
        raw = int(rule.amount)
    if raw <= 0:
        return 0
    scaled = (raw * int(multiplier_bps)) // 10000
    if rule.max_reward is not None:
        scaled = min(scaled, int(rule.max_reward))
    return max(0, int(scaled))


async def apply_event_rules(
    session: AsyncSession,
    *,
    user: BotUser,
    event_key: str,
    idempotency_prefix: str,
    order: Order | None = None,
    plan: Plan | None = None,
    reseller_id: int | None = None,
    description_override: str | None = None,
) -> list[PointsTransaction]:
    if not await loyalty_enabled(session, reseller_id=reseller_id):
        return []
    rules = await _rules_for_event(session, event_key, reseller_id=reseller_id)
    if not rules:
        return []
    gb = _plan_gb(plan)
    tier = await get_tier_for_points(session, int(user.points_balance or 0))
    out: list[PointsTransaction] = []
    for rule in rules:
        if not await _rule_passes(session, rule, user=user, order=order, plan=plan, gb=gb):
            continue
        pts = _compute_rule_amount(rule, gb=gb, multiplier_bps=tier.multiplier_bps)
        if pts <= 0:
            continue
        key = f"{idempotency_prefix}:rule:{rule.id}"
        tx = await credit_points(
            session,
            user,
            pts,
            tx_type="earn",
            source=f"rule:{rule.id}",
            reference=str(order.id) if order else None,
            description=description_override or rule.name,
            idempotency_key=key,
            meta={"event": event_key, "rule_id": rule.id},
            commit=True,
        )
        if tx:
            out.append(tx)
    return out


async def on_user_referred(
    session: AsyncSession,
    *,
    referred: BotUser,
    source: str = "telegram",
) -> None:
    if not referred.referred_by_id:
        return
    if int(referred.referred_by_id) == int(referred.id):
        referred.referred_by_id = None
        await session.commit()
        return
    try:
        await ensure_loyalty_defaults(session, reseller_id=None)
    except Exception:
        pass
    await record_referral_event(
        session,
        referrer_id=int(referred.referred_by_id),
        referred_id=int(referred.id),
        event_key="referral_signup",
        source=source,
        qualification_state="pending",
        idempotency_key=f"ref_signup:{referred.id}",
    )
    referrer = await session.get(BotUser, int(referred.referred_by_id))
    if referrer:
        await apply_event_rules(
            session,
            user=referrer,
            event_key="referral_signup",
            idempotency_prefix=f"ref_signup:{referred.id}",
            reseller_id=referred.reseller_id,
            description_override="ثبت‌نام با دعوت",
        )


async def _is_first_delivered_purchase(session: AsyncSession, order: Order) -> bool:
    note = (order.note or "").strip()
    if note.startswith("renew:") or note.startswith("reseller_app:"):
        return False
    prior = (
        await session.execute(
            select(Order.id)
            .where(
                Order.user_id == order.user_id,
                Order.status == "delivered",
                Order.id != order.id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return prior is None


async def on_order_delivered(session: AsyncSession, order: Order) -> None:
    """Award purchase / referral points after successful delivery. Idempotent."""
    note = (order.note or "").strip()
    if note.startswith("reseller_app:"):
        return
    user = order.user
    if user is None:
        user = await session.get(BotUser, order.user_id)
    if not user:
        return
    plan = order.plan
    if plan is None and order.plan_id:
        plan = await session.get(Plan, order.plan_id)
    reseller_id = order.reseller_id
    try:
        await ensure_loyalty_defaults(session, reseller_id=None)
    except Exception:
        logger.exception("ensure_loyalty_defaults failed")

    is_renew = note.startswith("renew:")
    if is_renew:
        await apply_event_rules(
            session,
            user=user,
            event_key="renewal",
            idempotency_prefix=f"order:{order.id}:renewal",
            order=order,
            plan=plan,
            reseller_id=reseller_id,
            description_override="تمدید موفق",
        )
        return

    first = await _is_first_delivered_purchase(session, order)
    await apply_event_rules(
        session,
        user=user,
        event_key="purchase",
        idempotency_prefix=f"order:{order.id}:purchase",
        order=order,
        plan=plan,
        reseller_id=reseller_id,
        description_override="خرید موفق",
    )
    if first:
        await apply_event_rules(
            session,
            user=user,
            event_key="first_purchase",
            idempotency_prefix=f"order:{order.id}:first_purchase",
            order=order,
            plan=plan,
            reseller_id=reseller_id,
            description_override="اولین خرید",
        )

    if user.referred_by_id:
        referrer = await session.get(BotUser, int(user.referred_by_id))
        if not referrer or int(referrer.id) == int(user.id):
            return
        # Qualify on first purchase
        await record_referral_event(
            session,
            referrer_id=int(referrer.id),
            referred_id=int(user.id),
            event_key="referral_qualification" if first else "referral_purchase",
            source="order",
            order_id=int(order.id),
            qualification_state="qualified" if first else "qualified",
            reward_state="pending",
            idempotency_key=f"ref_qual:{user.id}" if first else f"ref_purchase:{order.id}",
        )
        if first:
            await apply_event_rules(
                session,
                user=referrer,
                event_key="referral_first_purchase",
                idempotency_prefix=f"ref_first:{user.id}:order:{order.id}",
                order=order,
                plan=plan,
                reseller_id=reseller_id,
                description_override="اولین خرید دعوت‌شده",
            )
            await apply_event_rules(
                session,
                user=referrer,
                event_key="referral_qualification",
                idempotency_prefix=f"ref_qual_pts:{user.id}",
                order=order,
                plan=plan,
                reseller_id=reseller_id,
                description_override="واجد شرایط شدن دعوت",
            )
        else:
            await apply_event_rules(
                session,
                user=referrer,
                event_key="referral_purchase",
                idempotency_prefix=f"ref_purchase:{order.id}",
                order=order,
                plan=plan,
                reseller_id=reseller_id,
                description_override="خرید دعوت‌شده",
            )


async def reverse_order_points(session: AsyncSession, order: Order, *, reason: str) -> int:
    """Reverse all earn txs tied to this order reference. Returns count reversed."""
    rows = list(
        (
            await session.execute(
                select(PointsTransaction).where(
                    PointsTransaction.reference == str(order.id),
                    PointsTransaction.amount > 0,
                    PointsTransaction.tx_type == "earn",
                )
            )
        ).scalars().all()
    )
    n = 0
    for tx in rows:
        try:
            await reverse_points_tx(session, tx, reason=reason, commit=True)
            n += 1
        except Exception:
            logger.exception("reverse points failed tx=%s", tx.id)
    return n


async def list_points_history(
    session: AsyncSession, user_id: int, *, limit: int = 10, offset: int = 0
) -> list[PointsTransaction]:
    result = await session.execute(
        select(PointsTransaction)
        .where(PointsTransaction.user_id == user_id)
        .order_by(PointsTransaction.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def referral_stats(session: AsyncSession, user_id: int) -> dict[str, int]:
    total = int(
        (
            await session.execute(
                select(func.count()).select_from(BotUser).where(BotUser.referred_by_id == user_id)
            )
        ).scalar_one()
        or 0
    )
    qualified = int(
        (
            await session.execute(
                select(func.count())
                .select_from(ReferralEvent)
                .where(
                    ReferralEvent.referrer_id == user_id,
                    ReferralEvent.qualification_state == "qualified",
                )
            )
        ).scalar_one()
        or 0
    )
    earned = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(PointsTransaction.amount), 0)).where(
                    PointsTransaction.user_id == user_id,
                    PointsTransaction.amount > 0,
                    PointsTransaction.source.like("rule:%"),
                    PointsTransaction.description.like("%دعوت%"),
                )
            )
        ).scalar_one()
        or 0
    )
    # Broader: sum referral event-related earn txs
    if earned == 0:
        earned = int(
            (
                await session.execute(
                    select(func.coalesce(func.sum(PointsTransaction.amount), 0)).where(
                        PointsTransaction.user_id == user_id,
                        PointsTransaction.amount > 0,
                        PointsTransaction.idempotency_key.like("ref_%"),
                    )
                )
            ).scalar_one()
            or 0
        )
    return {"total": total, "qualified": qualified, "earned_points": earned}


async def month_earned_points(session: AsyncSession, user_id: int) -> int:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(
        (
            await session.execute(
                select(func.coalesce(func.sum(PointsTransaction.amount), 0)).where(
                    PointsTransaction.user_id == user_id,
                    PointsTransaction.amount > 0,
                    PointsTransaction.created_at >= start,
                )
            )
        ).scalar_one()
        or 0
    )


async def list_active_rewards(
    session: AsyncSession, *, reseller_id: int | None = None
) -> list[LoyaltyReward]:
    q = (
        select(LoyaltyReward)
        .where(
            LoyaltyReward.enabled.is_(True),
            LoyaltyReward.archived.is_(False),
        )
        .order_by(LoyaltyReward.sort_order.asc(), LoyaltyReward.id.asc())
    )
    if reseller_id is None:
        q = q.where(LoyaltyReward.reseller_id.is_(None))
    else:
        q = q.where(LoyaltyReward.reseller_id == int(reseller_id))
    rows = list((await session.execute(q)).scalars().all())
    if not rows and reseller_id is not None:
        q2 = (
            select(LoyaltyReward)
            .where(
                LoyaltyReward.enabled.is_(True),
                LoyaltyReward.archived.is_(False),
                LoyaltyReward.reseller_id.is_(None),
            )
            .order_by(LoyaltyReward.sort_order.asc(), LoyaltyReward.id.asc())
        )
        rows = list((await session.execute(q2)).scalars().all())
    return rows


async def _user_redemption_count(session: AsyncSession, user_id: int, reward_id: int) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(RewardRedemption)
                .where(
                    RewardRedemption.user_id == user_id,
                    RewardRedemption.reward_id == reward_id,
                    RewardRedemption.status == "completed",
                )
            )
        ).scalar_one()
        or 0
    )


async def redeem_reward(
    session: AsyncSession,
    user: BotUser,
    reward_id: int,
    *,
    service_id: int | None = None,
    idempotency_key: str | None = None,
) -> RewardRedemption:
    """Atomic redeem: lock reward + user, debit points, apply benefit, record redemption."""
    key = idempotency_key or f"redeem:{user.id}:{reward_id}:{int(datetime.now(timezone.utc).timestamp())}"
    existing = (
        await session.execute(
            select(RewardRedemption).where(RewardRedemption.idempotency_key == key)
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    # Lock reward row when supported (SQLite ignores / may no-op)
    try:
        reward = (
            await session.execute(
                select(LoyaltyReward).where(LoyaltyReward.id == int(reward_id)).with_for_update()
            )
        ).scalar_one_or_none()
    except Exception:
        reward = await session.get(LoyaltyReward, int(reward_id))
    if not reward or not reward.enabled or reward.archived:
        raise ValueError("این جایزه فعال نیست")
    if reward.max_redemptions_global is not None and int(reward.redemption_count) >= int(
        reward.max_redemptions_global
    ):
        raise ValueError("سقف کل بازخرید این جایزه پر شده")
    if reward.max_redemptions_per_user is not None:
        used = await _user_redemption_count(session, user.id, reward.id)
        if used >= int(reward.max_redemptions_per_user):
            raise ValueError("سقف بازخرید شما برای این جایزه پر شده")

    cost = int(reward.points_cost)
    if cost <= 0:
        raise ValueError("هزینه جایزه نامعتبر است")
    if int(user.points_balance or 0) < cost:
        raise ValueError("امتیاز کافی نیست")

    rtype = reward.reward_type
    rval = int(reward.reward_value)
    service: UserService | None = None
    wallet_reason: str | None = None

    if rtype in ("traffic_gb", "time_days"):
        if not service_id:
            raise ValueError("یک سرویس فعال انتخاب کنید")
        service = await session.get(UserService, int(service_id))
        if not service or int(service.bot_user_id) != int(user.id):
            raise ValueError("سرویس معتبر نیست")
        if not service.pg_user_id:
            raise ValueError("سرویس به پنل متصل نیست")
    elif rtype == "wallet_credit":
        if rval <= 0:
            raise ValueError("مقدار اعتبار نامعتبر است")
    elif rtype == "discount_percent":
        if rval <= 0 or rval > 100:
            raise ValueError("درصد تخفیف نامعتبر است")
    else:
        raise ValueError("نوع جایزه پشتیبانی نمی‌شود")

    # Debit points first (no commit) so failed apply rolls back the charge
    pts_tx = await debit_points(
        session,
        user,
        cost,
        tx_type="redeem",
        source=f"reward:{reward.id}",
        reference=str(reward.id),
        description=f"بازخرید: {reward.name}",
        idempotency_key=f"pts:{key}",
        meta={"reward_id": reward.id, "reward_type": rtype, "reward_value": rval},
        commit=False,
    )

    try:
        if rtype in ("traffic_gb", "time_days"):
            await _apply_service_reward(session, user, service, rtype, rval)
        elif rtype == "wallet_credit":
            wallet_reason = f"loyalty_reward:{reward.id}:{key}"
            from app.services.wallet import credit_wallet

            await credit_wallet(session, user, rval, wallet_reason, commit=False)
        reward.redemption_count = int(reward.redemption_count or 0) + 1
        red = RewardRedemption(
            user_id=user.id,
            reward_id=reward.id,
            points_spent=cost,
            reward_type=rtype,
            reward_value=rval,
            status="completed",
            service_id=service.id if service else None,
            points_tx_id=pts_tx.id if pts_tx else None,
            wallet_reason=wallet_reason,
            idempotency_key=key,
            meta_json=json.dumps({"reward_name": reward.name}, ensure_ascii=False),
        )
        session.add(red)
        await session.commit()
        await session.refresh(red)
        await session.refresh(user)
    except IntegrityError:
        await session.rollback()
        existing = (
            await session.execute(
                select(RewardRedemption).where(RewardRedemption.idempotency_key == key)
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        raise
    except Exception:
        await session.rollback()
        raise
    return red


async def _apply_service_reward(
    session: AsyncSession,
    user: BotUser,
    service: UserService,
    reward_type: str,
    reward_value: int,
) -> None:
    """Apply traffic/time to Pasarguard user (additive)."""
    import time

    from app.services.pasarguard import get_pg, get_pg_for_reseller

    if user.reseller_id:
        try:
            pg = await get_pg_for_reseller(session, int(user.reseller_id))
        except Exception:
            pg = get_pg()
    else:
        pg = get_pg()

    info = await pg.get_user_by_id(int(service.pg_user_id))
    payload: dict[str, Any] = {"status": "active"}
    if reward_type == "traffic_gb":
        add_bytes = int(reward_value) * (1024**3)
        current = info.get("data_limit")
        if current is None or int(current or 0) <= 0:
            # Unlimited — leave unlimited; still record redemption as granted meta
            payload["data_limit"] = 0
        else:
            payload["data_limit"] = int(current) + add_bytes
    elif reward_type == "time_days":
        add_sec = int(reward_value) * 86400
        expire = info.get("expire")
        # Pasarguard may return ISO or unix
        base = int(time.time())
        if expire:
            try:
                if isinstance(expire, (int, float)):
                    base = max(base, int(expire))
                else:
                    from datetime import datetime as dt

                    parsed = dt.fromisoformat(str(expire).replace("Z", "+00:00"))
                    base = max(base, int(parsed.timestamp()))
            except Exception:
                pass
        payload["expire"] = base + add_sec
    await pg.modify_user_by_id(int(service.pg_user_id), payload)


async def overview_metrics(session: AsyncSession) -> dict[str, Any]:
    total_refs = int(
        (
            await session.execute(
                select(func.count()).select_from(BotUser).where(BotUser.referred_by_id.is_not(None))
            )
        ).scalar_one()
        or 0
    )
    qualified = int(
        (
            await session.execute(
                select(func.count())
                .select_from(ReferralEvent)
                .where(ReferralEvent.qualification_state == "qualified")
            )
        ).scalar_one()
        or 0
    )
    issued = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(PointsTransaction.amount), 0)).where(
                    PointsTransaction.amount > 0
                )
            )
        ).scalar_one()
        or 0
    )
    redeemed = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(PointsTransaction.amount), 0)).where(
                    PointsTransaction.amount < 0,
                    PointsTransaction.tx_type == "redeem",
                )
            )
        ).scalar_one()
        or 0
    )
    wallet_credits = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(RewardRedemption.reward_value), 0)).where(
                    RewardRedemption.reward_type == "wallet_credit",
                    RewardRedemption.status == "completed",
                )
            )
        ).scalar_one()
        or 0
    )
    active_rewards = int(
        (
            await session.execute(
                select(func.count())
                .select_from(LoyaltyReward)
                .where(LoyaltyReward.enabled.is_(True), LoyaltyReward.archived.is_(False))
            )
        ).scalar_one()
        or 0
    )
    # Top referrers
    top_rows = (
        await session.execute(
            select(BotUser.referred_by_id, func.count())
            .where(BotUser.referred_by_id.is_not(None))
            .group_by(BotUser.referred_by_id)
            .order_by(func.count().desc())
            .limit(5)
        )
    ).all()
    top: list[dict[str, Any]] = []
    for rid, cnt in top_rows:
        u = await session.get(BotUser, int(rid))
        top.append(
            {
                "user_id": int(rid),
                "label": (u.username or u.full_name or str(u.telegram_id)) if u else str(rid),
                "count": int(cnt),
            }
        )
    return {
        "total_referrals": total_refs,
        "qualified_referrals": qualified,
        "points_issued": issued,
        "points_redeemed": abs(redeemed),
        "wallet_credits_issued": wallet_credits,
        "active_rewards": active_rewards,
        "top_referrers": top,
    }
