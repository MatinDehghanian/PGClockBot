"""Read a shop customer's service preview with a safe local fallback."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import BotUser, UserService
from app.services.authz import authz_from_staff, can_shop
from app.services.daily_report import format_jalali_parts
from app.services.formatting import format_bytes, format_expire
from app.services.numbers import to_fa_digits
from app.services.service_live_info import fetch_subscription_info
from app.services.service_scope import shop_services_clause
from app.services.service_status import service_status
from app.services.shop_membership import shop_member_clause
from app.services.shop_scope import resolve_shop_scope_id
from app.services.users_ops import build_user_ops_row

MAX_RECORD_ID = 2**31 - 1


@dataclass(slots=True)
class ServicePreview:
    username: str
    plan: str
    status: str
    status_title: str
    status_tone: str
    volume: str
    expire: str
    used: str = "—"
    remaining: str = "—"
    source: str = "آخرین اطلاعات ذخیره‌شده"
    warning: str = ""


def _local_preview(service: UserService, customer: BotUser) -> ServicePreview:
    summary = build_user_ops_row(customer, [service]).services[0]
    synced = service.quota_synced_at
    source = (
        "ذخیره‌شده در " + to_fa_digits(format_jalali_parts(synced)["date"])
        if synced else "اطلاعات اولیه؛ هنوز از پنل دریافت نشده"
    )
    return ServicePreview(
        username=service.pg_username,
        plan=service.plan.name if service.plan else "بدون پلن",
        status=summary.status.key,
        status_title=summary.status.title,
        status_tone=summary.status.tone,
        volume=summary.volume_text,
        expire=summary.expire_text,
        source=source,
    )


def _apply_live_info(preview: ServicePreview, info: dict) -> ServicePreview:
    if info.get("error"):
        preview.warning = info["error_message"]
        return preview
    status = service_status(info.get("status"))
    preview.status, preview.status_title, preview.status_tone = status.key, status.title, status.tone
    limit, used = info.get("data_limit"), info["used_traffic"]
    preview.volume = format_bytes(limit) if limit else "نامحدود"
    preview.used = format_bytes(used)
    preview.remaining = format_bytes(max(0, limit - used)) if limit else "نامحدود"
    preview.expire = format_expire(
        info.get("expire", info.get("expire_date")),
        status=status.key,
        expire_duration=info.get("expire_duration"),
    )
    preview.source = "اطلاعات زنده از پاسارگارد"
    return preview


async def load_user_service_preview(
    session: AsyncSession, staff: dict, *, customer_id: int, service_id: int
) -> ServicePreview:
    if not can_shop(authz_from_staff(staff), "dashboard"):
        raise PermissionError("دسترسی مجاز نیست")
    if any(type(value) is not int or not 1 <= value <= MAX_RECORD_ID for value in (customer_id, service_id)):
        raise ValueError("شناسه نامعتبر است")
    shop_id = resolve_shop_scope_id(staff)
    result = await session.execute(
        select(UserService, BotUser)
        .join(BotUser, UserService.bot_user_id == BotUser.id)
        .where(
            UserService.id == service_id,
            BotUser.id == customer_id,
            shop_services_clause(shop_id),
            shop_member_clause(shop_id),
        )
        .options(selectinload(UserService.plan))
        .limit(1)
    )
    row = result.one_or_none()
    if row is None:
        raise ValueError("سرویس یافت نشد")
    service, customer = row
    preview = _local_preview(service, customer)
    token, url, pg_id = service.subscription_token, service.subscription_url, service.pg_user_id
    # The panel can take seconds; end the read transaction before contacting it.
    await session.rollback()
    info = await fetch_subscription_info(
        token, subscription_url=url, service_id=service_id, expected_pg_user_id=pg_id
    )
    return _apply_live_info(preview, info)
