from __future__ import annotations

import json
import secrets
import string
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    BotUser,
    Order,
    OrderStatus,
    ResellerApplication,
    ResellerApplicationStatus,
    ResellerPlan,
    ResellerProfile,
    Role,
)

# Web panel sections a reseller may be granted
WEB_PERM_OPTIONS: list[tuple[str, str]] = [
    ("dashboard", "خانه / داشبورد"),
    ("orders", "سفارش‌ها"),
    ("payments", "پرداخت‌ها"),
    ("tickets", "تیکت‌ها"),
]

# Bot capabilities for resellers
BOT_PERM_OPTIONS: list[tuple[str, str]] = [
    ("stats", "مشاهده آمار نماینده"),
    ("approve_receipts", "تأیید رسید مشتریان"),
]

DEFAULT_WEB_PERMS = "dashboard,orders,payments,tickets"
DEFAULT_BOT_PERMS = "stats"


def parse_perms(raw: str | None) -> list[str]:
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            pass
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


def join_perms(items: Iterable[str] | None) -> str:
    return ",".join(sorted({str(x).strip() for x in (items or []) if str(x).strip()}))


def has_web_perm(profile: ResellerProfile | None, key: str, *, role: str | None = None) -> bool:
    if role == Role.ADMIN.value:
        return True
    if not profile or not profile.is_active:
        return False
    perms = parse_perms(profile.web_permissions) or parse_perms(DEFAULT_WEB_PERMS)
    return key in perms


def has_bot_perm(profile: ResellerProfile | None, key: str) -> bool:
    if not profile or not profile.is_active:
        return False
    if key == "approve_receipts":
        return bool(profile.can_approve_receipts) or "approve_receipts" in parse_perms(
            profile.bot_permissions
        )
    perms = parse_perms(profile.bot_permissions) or parse_perms(DEFAULT_BOT_PERMS)
    return key in perms


def _rand_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    # Ensure complexity for panel rules
    chars = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%"),
    ]
    chars += [secrets.choice(alphabet) for _ in range(max(0, length - 4))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _rand_username(prefix: str = "res") -> str:
    return f"{prefix}_{secrets.token_hex(3)}"


async def get_reseller_profile(session: AsyncSession, user_id: int) -> ResellerProfile | None:
    result = await session.execute(
        select(ResellerProfile).where(ResellerProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_active_reseller_plans(session: AsyncSession) -> list[ResellerPlan]:
    result = await session.execute(
        select(ResellerPlan)
        .where(ResellerPlan.is_active.is_(True))
        .order_by(ResellerPlan.sort_order, ResellerPlan.id)
    )
    return list(result.scalars().all())


async def list_reseller_plans(session: AsyncSession) -> list[ResellerPlan]:
    result = await session.execute(
        select(ResellerPlan).order_by(ResellerPlan.sort_order, ResellerPlan.id)
    )
    return list(result.scalars().all())


async def make_reseller(
    session: AsyncSession,
    user: BotUser,
    *,
    commission_percent: int = 10,
    can_approve_receipts: bool = False,
    pg_admin_username: str | None = None,
    pg_role_id: int | None = None,
    web_username: str | None = None,
    web_password_hash: str | None = None,
    web_permissions: str | None = None,
    bot_permissions: str | None = None,
    plan_id: int | None = None,
) -> ResellerProfile:
    user.role = Role.RESELLER.value
    result = await session.execute(
        select(ResellerProfile).where(ResellerProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    web_perms = web_permissions if web_permissions is not None else DEFAULT_WEB_PERMS
    bot_perms = bot_permissions if bot_permissions is not None else DEFAULT_BOT_PERMS
    if can_approve_receipts and "approve_receipts" not in parse_perms(bot_perms):
        bot_perms = join_perms(parse_perms(bot_perms) + ["approve_receipts"])
    if profile:
        profile.commission_percent = commission_percent
        profile.can_approve_receipts = can_approve_receipts
        profile.pg_admin_username = pg_admin_username
        profile.pg_role_id = pg_role_id
        if web_username:
            profile.web_username = web_username
        if web_password_hash:
            profile.web_password_hash = web_password_hash
        profile.web_permissions = web_perms
        profile.bot_permissions = bot_perms
        profile.plan_id = plan_id
        profile.is_active = True
    else:
        profile = ResellerProfile(
            user_id=user.id,
            commission_percent=commission_percent,
            can_approve_receipts=can_approve_receipts,
            pg_admin_username=pg_admin_username,
            pg_role_id=pg_role_id,
            web_username=web_username,
            web_password_hash=web_password_hash,
            web_permissions=web_perms,
            bot_permissions=bot_perms,
            plan_id=plan_id,
        )
        session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def create_application(
    session: AsyncSession,
    *,
    user: BotUser,
    plan: ResellerPlan,
    note: str | None = None,
) -> tuple[ResellerApplication, Order | None]:
    """Create application; if plan has price, also create a pending order."""
    if user.role == Role.RESELLER.value:
        raise ValueError("شما هم‌اکنون نماینده هستید")
    if user.role == Role.ADMIN.value:
        raise ValueError("ادمین نیاز به درخواست نمایندگی ندارد")

    existing = await session.execute(
        select(ResellerApplication).where(
            ResellerApplication.user_id == user.id,
            ResellerApplication.status.in_(
                [
                    ResellerApplicationStatus.PENDING_PAYMENT.value,
                    ResellerApplicationStatus.AWAITING_APPROVAL.value,
                ]
            ),
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("یک درخواست باز دارید؛ تا رسیدگی صبر کنید")

    app = ResellerApplication(
        user_id=user.id,
        plan_id=plan.id,
        note=note,
        status=(
            ResellerApplicationStatus.PENDING_PAYMENT.value
            if plan.price > 0
            else ResellerApplicationStatus.AWAITING_APPROVAL.value
        ),
    )
    session.add(app)
    await session.flush()

    order = None
    if plan.price > 0:
        order = Order(
            user_id=user.id,
            plan_id=None,
            amount=plan.price,
            status=OrderStatus.PENDING.value,
            note=f"reseller_app:{app.id}",
        )
        session.add(order)
        await session.flush()
        app.order_id = order.id

    await session.commit()
    await session.refresh(app)
    if order:
        await session.refresh(order)
    return app, order


async def get_application(session: AsyncSession, app_id: int) -> ResellerApplication | None:
    result = await session.execute(
        select(ResellerApplication)
        .options(
            selectinload(ResellerApplication.user),
            selectinload(ResellerApplication.plan),
        )
        .where(ResellerApplication.id == app_id)
    )
    return result.scalar_one_or_none()


async def list_applications(
    session: AsyncSession, *, status: str | None = None, limit: int = 100
) -> list[ResellerApplication]:
    q = (
        select(ResellerApplication)
        .options(
            selectinload(ResellerApplication.user),
            selectinload(ResellerApplication.plan),
        )
        .order_by(ResellerApplication.id.desc())
        .limit(limit)
    )
    if status:
        q = q.where(ResellerApplication.status == status)
    result = await session.execute(q)
    return list(result.scalars().all())


async def mark_application_paid(session: AsyncSession, order: Order) -> ResellerApplication | None:
    """When a reseller_app order is paid, move application to awaiting_approval."""
    note = order.note or ""
    if not note.startswith("reseller_app:"):
        return None
    try:
        app_id = int(note.split(":", 1)[1])
    except ValueError:
        return None
    app = await session.get(ResellerApplication, app_id)
    if not app:
        return None
    if app.status == ResellerApplicationStatus.PENDING_PAYMENT.value:
        app.status = ResellerApplicationStatus.AWAITING_APPROVAL.value
        await session.commit()
        await session.refresh(app)
    return app


async def provision_reseller(
    session: AsyncSession,
    *,
    user: BotUser,
    plan: ResellerPlan | None = None,
    commission_percent: int | None = None,
    can_approve_receipts: bool | None = None,
    web_permissions: str | None = None,
    bot_permissions: str | None = None,
    create_pg_admin: bool | None = None,
    create_web_access: bool | None = None,
    pg_role_id: int | None = None,
    panel_base_url: str = "",
) -> dict:
    """Create PG admin + web credentials + reseller profile. Returns plaintext secrets once."""
    from app.services.pasarguard import get_pg
    from app.services.web_auth import hash_password

    commission = (
        commission_percent
        if commission_percent is not None
        else (plan.commission_percent if plan else 10)
    )
    approve = (
        can_approve_receipts
        if can_approve_receipts is not None
        else (plan.can_approve_receipts if plan else False)
    )
    web_perms = web_permissions if web_permissions is not None else (
        plan.web_permissions if plan and plan.web_permissions else DEFAULT_WEB_PERMS
    )
    bot_perms = bot_permissions if bot_permissions is not None else (
        plan.bot_permissions if plan and plan.bot_permissions else DEFAULT_BOT_PERMS
    )
    do_pg = create_pg_admin if create_pg_admin is not None else (
        plan.create_pg_admin if plan else True
    )
    do_web = create_web_access if create_web_access is not None else (
        plan.create_web_access if plan else True
    )
    role_id = pg_role_id if pg_role_id is not None else (plan.pg_role_id if plan else None)

    pg_username = None
    pg_password = None
    if do_pg:
        pg_username = _rand_username("pg")
        pg_password = _rand_password(14)
        payload: dict = {
            "username": pg_username,
            "password": pg_password,
            "telegram_id": user.telegram_id,
            "note": f"PGClockBot reseller #{user.id}",
        }
        if role_id:
            payload["role_id"] = int(role_id)
        else:
            # Older Pasarguard panels
            payload["is_sudo"] = False
        try:
            await get_pg().create_admin(payload)
        except Exception as e:
            # Retry without role_id / with is_sudo only
            if "role_id" in payload:
                payload.pop("role_id", None)
                payload["is_sudo"] = False
                try:
                    await get_pg().create_admin(payload)
                except Exception as e2:
                    raise ValueError(f"ساخت ادمین پاسارگارد ناموفق: {e2}") from e2
            else:
                raise ValueError(f"ساخت ادمین پاسارگارد ناموفق: {e}") from e

    web_username = None
    web_password = None
    web_hash = None
    if do_web:
        web_username = _rand_username("web")
        web_password = _rand_password(12)
        web_hash = hash_password(web_password)

    profile = await make_reseller(
        session,
        user,
        commission_percent=commission,
        can_approve_receipts=approve,
        pg_admin_username=pg_username,
        pg_role_id=role_id,
        web_username=web_username,
        web_password_hash=web_hash,
        web_permissions=web_perms,
        bot_permissions=bot_perms,
        plan_id=plan.id if plan else None,
    )

    return {
        "profile": profile,
        "pg_username": pg_username,
        "pg_password": pg_password,
        "web_username": web_username,
        "web_password": web_password,
        "panel_url": panel_base_url.rstrip("/") if panel_base_url else "",
        "commission_percent": commission,
    }


def format_credentials_message(creds: dict) -> str:
    lines = [
        "✅ <b>درخواست نمایندگی تأیید شد</b>",
        "",
        f"کمیسیون شما: <b>{creds.get('commission_percent', 0)}٪</b>",
    ]
    if creds.get("web_username") and creds.get("web_password"):
        lines += [
            "",
            "🌐 <b>ورود به وب‌پنل</b>",
        ]
        if creds.get("panel_url"):
            lines.append(f"آدرس: {creds['panel_url']}")
        lines += [
            f"نام کاربری: <code>{creds['web_username']}</code>",
            f"رمز عبور: <code>{creds['web_password']}</code>",
        ]
    if creds.get("pg_username") and creds.get("pg_password"):
        lines += [
            "",
            "🛡 <b>پنل پاسارگارد</b>",
            f"نام کاربری: <code>{creds['pg_username']}</code>",
            f"رمز عبور: <code>{creds['pg_password']}</code>",
        ]
    lines += [
        "",
        "این اطلاعات را در جای امن نگه دارید.",
        "از منوی ربات می‌توانید به «پنل نماینده» دسترسی داشته باشید.",
    ]
    return "\n".join(lines)


async def approve_application(
    session: AsyncSession,
    app: ResellerApplication,
    *,
    reviewer_tg: int | None,
    panel_base_url: str = "",
    admin_note: str | None = None,
) -> dict:
    if app.status not in {
        ResellerApplicationStatus.AWAITING_APPROVAL.value,
        ResellerApplicationStatus.PENDING_PAYMENT.value,
    }:
        raise ValueError("این درخواست قابل تأیید نیست")
    user = await session.get(BotUser, app.user_id)
    plan = await session.get(ResellerPlan, app.plan_id)
    if not user or not plan:
        raise ValueError("کاربر یا پلن یافت نشد")
    if app.status == ResellerApplicationStatus.PENDING_PAYMENT.value and plan.price > 0:
        raise ValueError("هنوز پرداخت این درخواست تکمیل نشده")

    creds = await provision_reseller(
        session,
        user=user,
        plan=plan,
        panel_base_url=panel_base_url,
    )
    app.status = ResellerApplicationStatus.APPROVED.value
    app.reviewed_by = reviewer_tg
    if admin_note:
        app.admin_note = admin_note
    await session.commit()
    return creds


async def reject_application(
    session: AsyncSession,
    app: ResellerApplication,
    *,
    reviewer_tg: int | None,
    admin_note: str | None = None,
) -> None:
    if app.status in {
        ResellerApplicationStatus.APPROVED.value,
        ResellerApplicationStatus.REJECTED.value,
    }:
        raise ValueError("وضعیت درخواست قابل تغییر نیست")
    app.status = ResellerApplicationStatus.REJECTED.value
    app.reviewed_by = reviewer_tg
    if admin_note:
        app.admin_note = admin_note
    await session.commit()
