from __future__ import annotations

import json
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    BotUser,
    Order,
    OrderStatus,
    Payment,
    ResellerApplication,
    ResellerApplicationStatus,
    ResellerPlan,
    ResellerProfile,
    Role,
)

# Single permission set for BOTH web panel and bot (must stay identical).
FEATURE_PERMS: list[tuple[str, str]] = [
    ("dashboard", "خانه / داشبورد"),
    ("orders", "سفارش‌ها"),
    ("payments", "پرداخت‌ها و تأیید رسید"),
    ("tickets", "تیکت‌ها"),
    ("stats", "آمار و کمیسیون"),
]

# Back-compat aliases used by older templates
WEB_PERM_OPTIONS = FEATURE_PERMS
BOT_PERM_OPTIONS = [
    ("stats", "آمار نماینده"),
    ("payments", "تأیید رسید مشتریان"),
]

DEFAULT_FEATURE_PERMS = "dashboard,orders,payments,tickets,stats"
DEFAULT_WEB_PERMS = DEFAULT_FEATURE_PERMS
DEFAULT_BOT_PERMS = DEFAULT_FEATURE_PERMS

SETUP_TOKEN_HOURS = 48


async def get_reseller_panel_base_url(session: AsyncSession) -> str:
    """Custom reseller URL → PUBLIC_BASE_URL → http://{server_ip}:{WEB_PORT}."""
    from app.services.setup_wizard import default_panel_base_url
    from app.services.users import get_setting

    custom = (await get_setting(session, "reseller_panel_base_url") or "").strip().rstrip("/")
    if custom:
        return custom
    return default_panel_base_url()


async def get_reseller_pg_panel_base_url(session: AsyncSession) -> str:
    """Custom PG panel URL for resellers → else exact PG_BASE_URL from settings."""
    from app.config import get_settings, normalize_pg_base_url
    from app.services.users import get_setting

    custom = (await get_setting(session, "reseller_pg_panel_base_url") or "").strip()
    if custom:
        return normalize_pg_base_url(custom)
    return normalize_pg_base_url(get_settings().pg_base_url or "")


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
    allowed = {k for k, _ in FEATURE_PERMS}
    # Map legacy bot-only keys
    legacy = {"approve_receipts": "payments"}
    out: list[str] = []
    for p in raw.replace(";", ",").split(","):
        key = legacy.get(p.strip(), p.strip())
        if key in allowed and key not in out:
            out.append(key)
    return out


def join_perms(items: Iterable[str] | None) -> str:
    allowed = {k for k, _ in FEATURE_PERMS}
    return ",".join(sorted({str(x).strip() for x in (items or []) if str(x).strip() in allowed}))


def normalize_feature_perms(raw: str | None) -> str:
    perms = parse_perms(raw)
    return join_perms(perms) if perms else DEFAULT_FEATURE_PERMS


def has_perm(profile: ResellerProfile | None, key: str, *, role: str | None = None) -> bool:
    """Unified permission check for web + bot."""
    if role == Role.ADMIN.value:
        return True
    if not profile or not profile.is_active:
        return False
    perms = parse_perms(profile.web_permissions) or parse_perms(DEFAULT_FEATURE_PERMS)
    return key in perms


def has_web_perm(profile: ResellerProfile | None, key: str, *, role: str | None = None) -> bool:
    return has_perm(profile, key, role=role)


def has_bot_perm(profile: ResellerProfile | None, key: str) -> bool:
    if key == "approve_receipts":
        key = "payments"
    return has_perm(profile, key)


def setup_is_complete(profile: ResellerProfile | None) -> bool:
    """Reseller may log into web when credentials are provisioned (or wizard finished)."""
    if not profile or not profile.is_active:
        return False
    return bool(profile.setup_completed_at and profile.web_username and profile.web_password_hash)


async def reseller_owns_user(session: AsyncSession, reseller_user_id: int, customer_user_id: int) -> bool:
    customer = await session.get(BotUser, customer_user_id)
    return bool(customer and customer.reseller_id == reseller_user_id)


async def reseller_can_review_payment(
    session: AsyncSession,
    reviewer: BotUser,
    payment: Payment,
) -> bool:
    """Admins: yes. Resellers: payments perm + customer must belong to them."""
    if reviewer.role == Role.ADMIN.value:
        return True
    if reviewer.role != Role.RESELLER.value:
        return False
    profile = await get_reseller_profile(session, reviewer.id)
    if not has_bot_perm(profile, "payments"):
        return False
    return await reseller_owns_user(session, reviewer.id, payment.user_id)


def _rand_password(length: int = 14) -> str:
    """PasarGuard-compatible password: ≥14 chars, ≥2 lower, ≥2 upper, ≥1 special."""
    length = max(14, int(length))
    specials = "!@#$%^&*"
    required = (
        [secrets.choice(string.ascii_lowercase) for _ in range(2)]
        + [secrets.choice(string.ascii_uppercase) for _ in range(2)]
        + [secrets.choice(specials)]
        + [secrets.choice(string.digits) for _ in range(2)]
    )
    alphabet = string.ascii_letters + string.digits + specials
    required += [secrets.choice(alphabet) for _ in range(length - len(required))]
    secrets.SystemRandom().shuffle(required)
    return "".join(required)


def _rand_username(prefix: str = "res") -> str:
    return f"{prefix}_{secrets.token_hex(3)}"


async def _unique_web_username(session: AsyncSession, prefix: str = "web") -> str:
    for _ in range(12):
        uname = _rand_username(prefix)
        clash = await session.execute(
            select(ResellerProfile).where(ResellerProfile.web_username == uname)
        )
        if clash.scalar_one_or_none() is None:
            return uname
    return f"{prefix}_{secrets.token_hex(6)}"


def new_setup_token() -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=SETUP_TOKEN_HOURS)
    return token, expires


async def get_reseller_profile(session: AsyncSession, user_id: int) -> ResellerProfile | None:
    result = await session.execute(
        select(ResellerProfile).where(ResellerProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_profile_by_setup_token(session: AsyncSession, token: str) -> ResellerProfile | None:
    if not token or len(token) < 16:
        return None
    result = await session.execute(
        select(ResellerProfile).where(ResellerProfile.setup_token == token)
    )
    profile = result.scalar_one_or_none()
    if not profile or not profile.setup_token_expires:
        return None
    exp = profile.setup_token_expires
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        return None
    return profile


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
    issue_setup_token: bool = False,
) -> ResellerProfile:
    user.role = Role.RESELLER.value
    result = await session.execute(
        select(ResellerProfile).where(ResellerProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    # Force web/bot permissions identical
    perms = normalize_feature_perms(web_permissions or bot_permissions)
    if can_approve_receipts and "payments" not in parse_perms(perms):
        perms = join_perms(parse_perms(perms) + ["payments"])
    approve = "payments" in parse_perms(perms)

    if profile:
        profile.commission_percent = commission_percent
        profile.can_approve_receipts = approve
        if pg_admin_username is not None:
            profile.pg_admin_username = pg_admin_username
        if pg_role_id is not None:
            profile.pg_role_id = pg_role_id
        if web_username:
            profile.web_username = web_username
        if web_password_hash:
            profile.web_password_hash = web_password_hash
        profile.web_permissions = perms
        profile.bot_permissions = perms
        profile.plan_id = plan_id
        profile.is_active = True
    else:
        profile = ResellerProfile(
            user_id=user.id,
            commission_percent=commission_percent,
            can_approve_receipts=approve,
            pg_admin_username=pg_admin_username,
            pg_role_id=pg_role_id,
            web_username=web_username,
            web_password_hash=web_password_hash,
            web_permissions=perms,
            bot_permissions=perms,
            plan_id=plan_id,
        )
        session.add(profile)

    if issue_setup_token:
        token, expires = new_setup_token()
        profile.setup_token = token
        profile.setup_token_expires = expires
        # Web creds already provisioned → keep login unlocked; token is for bot only
        if web_username and web_password_hash:
            profile.setup_completed_at = datetime.now(timezone.utc)
        else:
            profile.setup_completed_at = None

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
    share_pg_panel_url: bool | None = None,
    pg_role_id: int | None = None,
    panel_base_url: str = "",
) -> dict:
    """Activate reseller: PG admin + web panel creds + optional bot-token setup link."""
    from app.services.pasarguard import get_pg
    from app.services.web_auth import hash_password

    commission = (
        commission_percent
        if commission_percent is not None
        else (plan.commission_percent if plan else 10)
    )
    perms = normalize_feature_perms(
        web_permissions
        or bot_permissions
        or (plan.web_permissions if plan else None)
        or (plan.bot_permissions if plan else None)
    )
    if can_approve_receipts and "payments" not in parse_perms(perms):
        perms = join_perms(parse_perms(perms) + ["payments"])
    approve = "payments" in parse_perms(perms)

    role_id = pg_role_id if pg_role_id is not None else (plan.pg_role_id if plan else None)
    if create_pg_admin is not None:
        do_pg = bool(create_pg_admin)
    elif plan is not None:
        do_pg = bool(plan.create_pg_admin) or bool(role_id)
    else:
        do_pg = True

    do_web = True if create_web_access is None else bool(create_web_access)
    if share_pg_panel_url is not None:
        share_pg = bool(share_pg_panel_url)
    elif plan is not None:
        share_pg = bool(getattr(plan, "share_pg_panel_url", False))
    else:
        share_pg = False

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
            payload["is_sudo"] = False
        try:
            await get_pg().create_admin(payload)
        except Exception as e:
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
        web_username = await _unique_web_username(session, "web")
        web_password = _rand_password(14)
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
        web_permissions=perms,
        bot_permissions=perms,
        plan_id=plan.id if plan else None,
        issue_setup_token=True,
    )
    profile.share_pg_panel_url = share_pg
    await session.commit()
    await session.refresh(profile)

    base = (panel_base_url or "").rstrip("/")
    if not base:
        base = await get_reseller_panel_base_url(session)
    setup_url = f"{base}/rsetup/{profile.setup_token}" if base and profile.setup_token else ""
    pg_panel = await get_reseller_pg_panel_base_url(session) if share_pg else ""

    return {
        "profile": profile,
        "pg_username": pg_username if share_pg else None,
        "pg_password": pg_password if share_pg else None,
        "pg_panel_url": pg_panel,
        "share_pg_panel_url": share_pg,
        "web_username": web_username,
        "web_password": web_password,
        "setup_url": setup_url,
        "setup_token": profile.setup_token,
        "panel_url": base,
        "commission_percent": commission,
        "permissions": perms,
    }


def format_credentials_message(creds: dict) -> str:
    """Deliver PG + web panel URLs/credentials (and optional bot setup link)."""
    lines = [
        "✅ <b>نمایندگی فعال شد</b>",
        "",
        f"کمیسیون شما: <b>{creds.get('commission_percent', 0)}٪</b>",
    ]

    pg_panel = (creds.get("pg_panel_url") or "").strip().rstrip("/")
    share_pg = bool(creds.get("share_pg_panel_url")) or bool(pg_panel and creds.get("pg_username"))
    if share_pg or creds.get("pg_username"):
        lines += ["", "🛡 <b>پنل پاسارگارد</b>"]
        if pg_panel:
            lines.append(f"آدرس پنل: {pg_panel}")
        if creds.get("pg_username") and creds.get("pg_password"):
            lines += [
                f"نام کاربری: <code>{creds['pg_username']}</code>",
                f"رمز: <code>{creds['pg_password']}</code>",
                "رمز را عوض کنید و در جای امن نگه دارید.",
            ]
        elif not pg_panel:
            lines.append("ادمین پاسارگارد برای این پلن ساخته نشد.")
    else:
        lines += [
            "",
            "🛡 مدیریت VPN از طریق همین وب‌پنل ربات انجام می‌شود (لینک پنل پاسارگارد ارسال نشده).",
        ]

    panel = (creds.get("panel_url") or "").strip().rstrip("/")
    lines += ["", "🌐 <b>وب‌پنل ربات (نماینده)</b>"]
    if panel:
        lines += [f"آدرس پنل: {panel}", f"آدرس ورود: {panel}/login"]
    else:
        lines.append("آدرس پنل هنوز تنظیم نشده — از ادمین بپرسید.")
    if creds.get("web_username") and creds.get("web_password"):
        lines += [
            f"نام کاربری: <code>{creds['web_username']}</code>",
            f"رمز: <code>{creds['web_password']}</code>",
        ]

    if creds.get("setup_url"):
        lines += [
            "",
            "🤖 <b>ربات اختصاصی (اختیاری)</b>",
            "برای ثبت توکن ربات خودتان از @BotFather:",
            creds["setup_url"],
            "لینک یک‌بارمصرف است — با کسی به اشتراک نگذارید.",
        ]

    lines += ["", "از منوی ربات به امکانات مجاز «پنل نماینده» دسترسی دارید."]
    return "\n".join(lines)


async def complete_reseller_setup(
    session: AsyncSession,
    profile: ResellerProfile,
    *,
    web_username: str | None = None,
    password_hash: str | None = None,
    bot_token: str | None = None,
    bot_username: str | None = None,
    bot_only: bool = False,
) -> ResellerProfile:
    """Finalize setup wizard. bot_only=True updates bot token when web creds already exist."""
    if not bot_only:
        uname = (web_username or "").strip().lower()
        if len(uname) < 3:
            raise ValueError("نام کاربری حداقل ۳ کاراکتر باشد")
        clash = await session.execute(
            select(ResellerProfile).where(
                ResellerProfile.web_username == uname,
                ResellerProfile.id != profile.id,
            )
        )
        if clash.scalar_one_or_none():
            raise ValueError("این نام کاربری قبلاً گرفته شده")
        if not password_hash:
            raise ValueError("رمز عبور الزامی است")
        profile.web_username = uname
        profile.web_password_hash = password_hash

    if bot_token:
        token = bot_token.strip()
        from app.config import get_settings

        main_token = (get_settings().bot_token or "").strip()
        if main_token and token == main_token:
            raise ValueError("نمی‌توانید توکن ربات اصلی ادمین را ثبت کنید — ربات اختصاصی بسازید")
        clash_bot = await session.execute(
            select(ResellerProfile).where(
                ResellerProfile.bot_token == token,
                ResellerProfile.id != profile.id,
            )
        )
        if clash_bot.scalar_one_or_none():
            raise ValueError("این توکن ربات قبلاً برای نماینده دیگری ثبت شده")
        profile.bot_token = token
        profile.bot_username = (bot_username or "").lstrip("@") or None
    elif not bot_only:
        raise ValueError("توکن ربات الزامی است")

    profile.setup_token = None
    profile.setup_token_expires = None
    profile.setup_completed_at = datetime.now(timezone.utc)
    profile.web_permissions = normalize_feature_perms(profile.web_permissions)
    profile.bot_permissions = profile.web_permissions
    profile.can_approve_receipts = "payments" in parse_perms(profile.web_permissions)
    await session.commit()
    await session.refresh(profile)
    return profile


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


async def revoke_reseller(
    session: AsyncSession,
    user_id: int,
    *,
    delete_pg_admin: bool = True,
    commit: bool = True,
    reason: str | None = None,
) -> dict:
    """Remove reseller profile, unlink customers, demote role to user.

    Does not delete the BotUser row. Optional PasarGuard admin cleanup.
    """
    from sqlalchemy import update

    from app.services.pasarguard import get_pg

    user = await session.get(BotUser, user_id)
    if not user:
        raise ValueError("کاربر یافت نشد")
    profile = await get_reseller_profile(session, user_id)
    if not profile:
        raise ValueError("این کاربر نماینده نیست")

    pg_username = (profile.pg_admin_username or "").strip() or None
    pg_deleted = False
    if delete_pg_admin and pg_username:
        try:
            await get_pg().delete_admin(pg_username)
            pg_deleted = True
        except Exception:
            pg_deleted = False

    await session.execute(
        update(BotUser).where(BotUser.reseller_id == user_id).values(reseller_id=None)
    )
    await session.execute(
        update(Order).where(Order.reseller_id == user_id).values(reseller_id=None)
    )

    await session.delete(profile)
    if user.role == Role.RESELLER.value:
        user.role = Role.USER.value

    if commit:
        await session.commit()
        await session.refresh(user)

    return {
        "user_id": user_id,
        "telegram_id": user.telegram_id,
        "pg_admin_username": pg_username,
        "pg_admin_deleted": pg_deleted,
        "reason": (reason or "").strip() or None,
    }


def format_revoke_message(reason: str) -> str:
    """Notify former reseller that their agency access was removed."""
    reason = (reason or "").strip()
    lines = [
        "❌ <b>نمایندگی شما حذف شد</b>",
        "",
        "دسترسی پنل نماینده و ادمین پاسارگارد مرتبط لغو شده است.",
    ]
    if reason:
        lines += ["", f"علت: {reason}"]
    lines += ["", "در صورت نیاز با پشتیبانی در ارتباط باشید."]
    return "\n".join(lines)


async def notify_reseller_revoked(telegram_id: int, reason: str) -> bool:
    """Best-effort Telegram notice after revoke. Returns True if sent."""
    try:
        from app.bot import create_bot

        bot = create_bot()
        try:
            await bot.send_message(
                telegram_id,
                format_revoke_message(reason),
                parse_mode="HTML",
            )
            return True
        finally:
            await bot.session.close()
    except Exception:
        return False
