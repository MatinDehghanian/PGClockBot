"""Reseller capacity: renew package / buy extra volume & user slots."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, ResellerPlan, ResellerProfile
from app.services.billing import GB, is_payg
from app.services.formatting import format_toman

logger = logging.getLogger(__name__)

# Whitelist quantities exposed in Telegram buttons — reject forged callback amounts.
ALLOWED_EXTRA_GB = frozenset({1, 5, 10, 50})
ALLOWED_EXTRA_USERS = frozenset({1, 5, 10, 20})


def plan_allows_buy_extra(plan: ResellerPlan | None) -> bool:
    if plan is None:
        return False
    return bool(getattr(plan, "allow_buy_extra", False))


def plan_extra_gb_price(plan: ResellerPlan | None) -> int:
    if plan is None:
        return 0
    return max(0, int(getattr(plan, "extra_gb_price", 0) or 0))


def plan_extra_user_price(plan: ResellerPlan | None) -> int:
    if plan is None:
        return 0
    return max(0, int(getattr(plan, "extra_user_price", 0) or 0))


def plan_renew_price(plan: ResellerPlan | None) -> int:
    """Flat renew base (legacy). Prefer compute_renew_invoice for full quote."""
    from app.services.pg_admin_subscription import renew_base_amount

    return renew_base_amount(plan)


async def load_reseller_plan(
    session: AsyncSession, profile: ResellerProfile
) -> ResellerPlan | None:
    plan_id = getattr(profile, "plan_id", None)
    if not plan_id:
        return None
    return await session.get(ResellerPlan, int(plan_id))


async def _charge_wallet(session: AsyncSession, user: BotUser, amount: int) -> None:
    """Atomically debit shop wallet (optimistic lock on balance)."""
    if amount <= 0:
        return
    uid = int(user.id)
    need = int(amount)
    bal = int(user.wallet_balance or 0)
    if bal < need:
        raise ValueError(
            f"موجودی کیف پول کافی نیست.\n"
            f"لازم: {format_toman(need)}\n"
            f"موجودی: {format_toman(bal)}"
        )
    with session.no_autoflush:
        result = await session.execute(
            update(BotUser)
            .where(BotUser.id == uid, BotUser.wallet_balance >= need)
            .values(wallet_balance=BotUser.wallet_balance - need)
            .execution_options(synchronize_session=False)
        )
    if result.rowcount != 1:
        await session.refresh(user)
        raise ValueError(
            f"موجودی کیف پول کافی نیست.\n"
            f"لازم: {format_toman(need)}\n"
            f"موجودی: {format_toman(int(user.wallet_balance or 0))}"
        )
    await session.refresh(user)


async def _refund_wallet(session: AsyncSession, user: BotUser, amount: int) -> None:
    if amount <= 0:
        return
    uid = int(user.id)
    with session.no_autoflush:
        await session.execute(
            update(BotUser)
            .where(BotUser.id == uid)
            .values(wallet_balance=BotUser.wallet_balance + int(amount))
            .execution_options(synchronize_session=False)
        )
    await session.refresh(user)


def _admin_max_users(admin: dict) -> int:
    overrides = admin.get("permission_overrides")
    if isinstance(overrides, dict) and overrides.get("max_users") is not None:
        try:
            return max(0, int(overrides["max_users"]))
        except (TypeError, ValueError):
            pass
    for key in ("max_users", "users_max"):
        if admin.get(key) is not None:
            try:
                return max(0, int(admin[key]))
            except (TypeError, ValueError):
                pass
    role = admin.get("role") if isinstance(admin.get("role"), dict) else {}
    limits = role.get("limits") if isinstance(role, dict) else {}
    if isinstance(limits, dict) and limits.get("max_users") is not None:
        try:
            return max(0, int(limits["max_users"]))
        except (TypeError, ValueError):
            pass
    return 0


def _admin_data_limit(admin: dict) -> int:
    for key in ("data_limit",):
        if admin.get(key) is not None:
            try:
                return max(0, int(admin[key]))
            except (TypeError, ValueError):
                pass
    return 0


async def buy_extra_gb(
    session: AsyncSession,
    *,
    user: BotUser,
    profile: ResellerProfile,
    plan: ResellerPlan,
    gb: int,
) -> dict[str, Any]:
    if not plan_allows_buy_extra(plan):
        raise ValueError("این پلن امکان خرید حجم اضافه ندارد")
    try:
        gb_n = int(gb)
    except (TypeError, ValueError) as e:
        raise ValueError("مقدار حجم نامعتبر است") from e
    if gb_n not in ALLOWED_EXTRA_GB:
        raise ValueError("مقدار حجم مجاز نیست")
    price = plan_extra_gb_price(plan)
    if price <= 0:
        raise ValueError("قیمت حجم اضافه برای این پلن تعریف نشده است")
    if is_payg(profile):
        from app.services.billing import payg_available_balance

        if await payg_available_balance(session, profile) <= 0:
            raise ValueError("موجودی کیف پول تمام شده — ابتدا شارژ و رفع مسدودی کنید")

    uname = (profile.pg_admin_username or "").strip()
    if not uname:
        raise ValueError("ادمین پاسارگارد برای این نماینده تنظیم نشده است")

    total = price * gb_n
    from app.services.wallet import credit_wallet, debit_wallet

    await debit_wallet(
        session, user, total, reason=f"reseller_extra_gb:{gb_n}:{uname}", commit=False
    )

    from app.services.pasarguard import get_pg

    pg = get_pg()
    try:
        admin = await pg.get_admin(uname)
        if not isinstance(admin, dict):
            raise ValueError("ادمین پاسارگارد یافت نشد")
        current = _admin_data_limit(admin)
        # If unlimited (0), start from purchased amount
        new_limit = (current if current > 0 else 0) + gb_n * GB
        await pg.modify_admin(uname, {"data_limit": int(new_limit)})
    except ValueError:
        await credit_wallet(
            session, user, total, reason=f"reseller_extra_gb_refund:{gb_n}:{uname}", commit=False
        )
        await session.commit()
        raise
    except Exception as e:
        await credit_wallet(
            session, user, total, reason=f"reseller_extra_gb_refund:{gb_n}:{uname}", commit=False
        )
        await session.commit()
        logger.exception("buy_extra_gb PG failed admin=%s", uname)
        raise ValueError("افزایش حجم در پاسارگارد ناموفق بود — مبلغ بازگردانده شد") from e

    from app.services.pg_admin_subscription import record_unit_extra

    await record_unit_extra(session, pg_username=uname, gb=gb_n, users=0)
    await session.commit()
    return {"gb": gb_n, "amount": total, "data_limit": new_limit}


async def buy_extra_users(
    session: AsyncSession,
    *,
    user: BotUser,
    profile: ResellerProfile,
    plan: ResellerPlan,
    count: int,
) -> dict[str, Any]:
    if not plan_allows_buy_extra(plan):
        raise ValueError("این پلن امکان خرید کاربر اضافه ندارد")
    try:
        n = int(count)
    except (TypeError, ValueError) as e:
        raise ValueError("تعداد کاربر نامعتبر است") from e
    if n not in ALLOWED_EXTRA_USERS:
        raise ValueError("تعداد کاربر مجاز نیست")
    price = plan_extra_user_price(plan)
    if price <= 0:
        raise ValueError("قیمت کاربر اضافه برای این پلن تعریف نشده است")
    if is_payg(profile):
        from app.services.billing import payg_available_balance

        if await payg_available_balance(session, profile) <= 0:
            raise ValueError("موجودی کیف پول تمام شده — ابتدا شارژ و رفع مسدودی کنید")

    uname = (profile.pg_admin_username or "").strip()
    if not uname:
        raise ValueError("ادمین پاسارگارد برای این نماینده تنظیم نشده است")

    total = price * n
    from app.services.wallet import credit_wallet, debit_wallet

    await debit_wallet(
        session, user, total, reason=f"reseller_extra_users:{n}:{uname}", commit=False
    )

    from app.services.pasarguard import get_pg

    pg = get_pg()
    try:
        admin = await pg.get_admin(uname)
        if not isinstance(admin, dict):
            raise ValueError("ادمین پاسارگارد یافت نشد")
        current = _admin_max_users(admin)
        new_max = current + n
        overrides = (
            dict(admin.get("permission_overrides") or {})
            if isinstance(admin.get("permission_overrides"), dict)
            else {}
        )
        overrides["max_users"] = int(new_max)
        await pg.modify_admin(
            uname, {"permission_overrides": overrides, "max_users": int(new_max)}
        )
    except ValueError:
        await credit_wallet(
            session, user, total, reason=f"reseller_extra_users_refund:{n}:{uname}", commit=False
        )
        await session.commit()
        raise
    except Exception as e:
        await credit_wallet(
            session, user, total, reason=f"reseller_extra_users_refund:{n}:{uname}", commit=False
        )
        await session.commit()
        logger.exception("buy_extra_users PG failed admin=%s", uname)
        raise ValueError("افزایش کاربر در پاسارگارد ناموفق بود — مبلغ بازگردانده شد") from e

    from app.services.pg_admin_subscription import record_unit_extra

    await record_unit_extra(session, pg_username=uname, gb=0, users=n)
    await session.commit()
    return {"users": n, "amount": total, "max_users": new_max}


async def renew_reseller_capacity(
    session: AsyncSession,
    *,
    user: BotUser,
    profile: ResellerProfile,
    plan: ResellerPlan,
) -> dict[str, Any]:
    """Renew subscription: invoice from capacity, restore access, reset traffic."""
    from app.services.pg_admin_subscription import (
        get_or_create_subscription,
        is_subscription_plan,
        renew_subscription,
    )

    if is_payg(profile):
        raise ValueError("پلن PAYG تمدید زمانی ندارد — از شارژ کیف پول استفاده کنید")
    if not is_subscription_plan(plan):
        raise ValueError("تمدید فقط برای پلن اشتراک است")

    uname = (profile.pg_admin_username or "").strip()
    if not uname:
        raise ValueError("ادمین پاسارگارد برای این نماینده تنظیم نشده است")

    sub = await get_or_create_subscription(session, uname)
    if sub.plan_id is None:
        sub.plan_id = int(plan.id)
    result = await renew_subscription(
        session,
        sub=sub,
        plan=plan,
        payer=user,
        charge_wallet=True,
        reset_user_traffic=True,
    )
    return {
        "amount": result.get("amount", 0),
        "reset_ok": result.get("reset_ok", 0),
        "reset_err": result.get("reset_err", 0),
        "invoice": result.get("invoice"),
        "expires_at": result.get("expires_at"),
    }
