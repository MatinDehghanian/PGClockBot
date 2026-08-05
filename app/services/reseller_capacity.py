"""Reseller capacity: renew package / buy extra volume & user slots."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, ResellerPlan, ResellerProfile
from app.services.billing import GB, is_payg
from app.services.formatting import format_toman

logger = logging.getLogger(__name__)


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
    if plan is None:
        return 0
    renew = int(getattr(plan, "renew_price", 0) or 0)
    if renew > 0:
        return renew
    return max(0, int(getattr(plan, "price", 0) or 0))


async def load_reseller_plan(
    session: AsyncSession, profile: ResellerProfile
) -> ResellerPlan | None:
    plan_id = getattr(profile, "plan_id", None)
    if not plan_id:
        return None
    return await session.get(ResellerPlan, int(plan_id))


async def _charge_wallet(session: AsyncSession, user: BotUser, amount: int) -> None:
    if amount <= 0:
        return
    bal = int(user.wallet_balance or 0)
    if bal < amount:
        raise ValueError(
            f"موجودی کیف پول کافی نیست.\n"
            f"لازم: {format_toman(amount)}\n"
            f"موجودی: {format_toman(bal)}"
        )
    user.wallet_balance = bal - int(amount)


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
    gb_n = max(1, int(gb))
    price = plan_extra_gb_price(plan)
    if price <= 0:
        raise ValueError("قیمت حجم اضافه برای این پلن تعریف نشده است")
    if is_payg(profile) and int(profile.billing_balance or 0) <= 0:
        raise ValueError("موجودی PAYG تمام شده — ابتدا شارژ و رفع مسدودی کنید")

    uname = (profile.pg_admin_username or "").strip()
    if not uname:
        raise ValueError("ادمین پاسارگارد برای این نماینده تنظیم نشده است")

    total = price * gb_n
    await _charge_wallet(session, user, total)

    from app.services.pasarguard import get_pg

    pg = get_pg()
    admin = await pg.get_admin(uname)
    if not isinstance(admin, dict):
        user.wallet_balance = int(user.wallet_balance or 0) + total
        raise ValueError("ادمین پاسارگارد یافت نشد")

    current = _admin_data_limit(admin)
    # If unlimited (0), start from purchased amount
    new_limit = (current if current > 0 else 0) + gb_n * GB
    await pg.modify_admin(uname, {"data_limit": int(new_limit)})
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
    n = max(1, int(count))
    price = plan_extra_user_price(plan)
    if price <= 0:
        raise ValueError("قیمت کاربر اضافه برای این پلن تعریف نشده است")
    if is_payg(profile) and int(profile.billing_balance or 0) <= 0:
        raise ValueError("موجودی PAYG تمام شده — ابتدا شارژ و رفع مسدودی کنید")

    uname = (profile.pg_admin_username or "").strip()
    if not uname:
        raise ValueError("ادمین پاسارگارد برای این نماینده تنظیم نشده است")

    total = price * n
    await _charge_wallet(session, user, total)

    from app.services.pasarguard import get_pg

    pg = get_pg()
    admin = await pg.get_admin(uname)
    if not isinstance(admin, dict):
        user.wallet_balance = int(user.wallet_balance or 0) + total
        raise ValueError("ادمین پاسارگارد یافت نشد")

    current = _admin_max_users(admin)
    new_max = current + n
    overrides = dict(admin.get("permission_overrides") or {}) if isinstance(
        admin.get("permission_overrides"), dict
    ) else {}
    overrides["max_users"] = int(new_max)
    await pg.modify_admin(uname, {"permission_overrides": overrides, "max_users": int(new_max)})
    await session.commit()
    return {"users": n, "amount": total, "max_users": new_max}


async def renew_reseller_capacity(
    session: AsyncSession,
    *,
    user: BotUser,
    profile: ResellerProfile,
    plan: ResellerPlan,
) -> dict[str, Any]:
    """Renew: charge renew_price and reset traffic on owned PG users."""
    amount = plan_renew_price(plan)
    if is_payg(profile) and int(profile.billing_balance or 0) <= 0:
        raise ValueError("موجودی PAYG تمام شده — ابتدا شارژ و رفع مسدودی کنید")

    uname = (profile.pg_admin_username or "").strip()
    if not uname:
        raise ValueError("ادمین پاسارگارد برای این نماینده تنظیم نشده است")

    await _charge_wallet(session, user, amount)

    from app.services.billing_suspend import list_owned_user_ids
    from app.services.pasarguard import get_pg

    pg = get_pg()
    reset_ok = 0
    reset_err = 0
    for uid in await list_owned_user_ids(pg, uname):
        try:
            await pg.reset_user_by_id(uid)
            reset_ok += 1
        except Exception:
            reset_err += 1
            logger.debug("renew reset user %s failed", uid, exc_info=True)

    await session.commit()
    return {"amount": amount, "reset_ok": reset_ok, "reset_err": reset_err}
