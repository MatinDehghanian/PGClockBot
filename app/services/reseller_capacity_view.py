"""What the reseller screen shows about a PasarGuard subscription's capacity, and the manual re-sync."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PgAdminSubscription, ResellerPlan, ResellerProfile
from app.services.pg_admin_subscription import (
    PgCapacityUnreadable,
    get_subscription,
    is_current_capacity_plan,
    read_live_pg_admin_capacity,
)

UNLIMITED = "نامحدود"
NO_SUBSCRIPTION = "اشتراک پاسارگارد برای این نماینده یافت نشد"
NOT_CURRENT_CAPACITY = "همگام‌سازی فقط برای نمایندگانی است که با پلن «ظرفیت فعلی» اعطا شده‌اند"
NO_PG_ADMIN = "ادمین پاسارگارد برای این نماینده تنظیم نشده است"
BYTES_PER_GB = 1024**3


@dataclass(frozen=True, slots=True)
class LiveCapacity:
    gb: int
    users: int


def live_capacity_from_overview(overview: dict[str, Any] | None) -> LiveCapacity | None:
    """Live limits out of the reseller PasarGuard overview, or ``None`` when it was not readable."""
    if not overview or not overview.get("ready"):
        return None
    traffic_limit = int((overview.get("traffic") or {}).get("limit") or 0)
    users_limit = int((overview.get("users") or {}).get("limit") or 0)
    return LiveCapacity(gb=math.ceil(traffic_limit / BYTES_PER_GB) if traffic_limit > 0 else 0, users=users_limit)


def _amount(value: int, unit: str) -> str:
    return f"{value} {unit}" if value > 0 else UNLIMITED


def build_capacity_view(
    sub: PgAdminSubscription,
    *,
    current_capacity: bool,
    live: LiveCapacity | None,
    allocation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stored capacity as text («نامحدود» for zero), and how it differs from the live panel limits."""
    base_gb, base_users = int(sub.base_gb or 0), int(sub.base_users or 0)
    extra_gb, extra_users = int(sub.extra_gb_purchased or 0), int(sub.extra_users_purchased or 0)
    total_gb, total_users = base_gb + extra_gb, base_users + extra_users
    differs = bool(current_capacity and live is not None and (live.gb != total_gb or live.users != total_users))
    view: dict[str, Any] = {
        "total_gb_text": _amount(total_gb, "گیگ"),
        "extra_gb_text": f"{extra_gb} گیگ",
        "total_users_text": _amount(total_users, "کاربر"),
        "extra_users_text": f"{extra_users} کاربر",
        "live_gb_text": _amount(live.gb, "گیگ") if live is not None else "خوانده نشد",
        "live_users_text": _amount(live.users, "کاربر") if live is not None else "خوانده نشد",
        "live_known": live is not None,
        "differs": differs,
        "can_sync": bool(current_capacity),
    }
    if allocation:
        view.update(allocation)
    return view


async def allocation_view_for_shop(
    session: AsyncSession, shop_id: int
) -> dict[str, Any]:
    """Allocation / ceiling block for the reseller capacity page."""
    from app.services.formatting import format_bytes
    from app.services.volume_allocation import build_allocation_snapshot

    snap = await build_allocation_snapshot(session, int(shop_id))
    if snap is None:
        return {}
    ceiling_text = (
        format_bytes(snap.ceiling_bytes) if snap.ceiling_bytes is not None else "نامشخص"
    )
    view = {
        "alloc_bytes_text": format_bytes(snap.allocated_bytes),
        "alloc_ceiling_text": ceiling_text,
        "alloc_ratio_text": f"{format_bytes(snap.allocated_bytes)} / {ceiling_text}",
        "alloc_local_text": format_bytes(snap.local_allocated_bytes),
        "alloc_external_text": format_bytes(snap.external_allocated_bytes),
        "alloc_expired_held_text": format_bytes(snap.expired_held_bytes),
        "alloc_unlimited": snap.unlimited_services,
        "alloc_is_oversold": snap.is_oversold,
        "alloc_allow_oversell": snap.allow_oversell,
        "alloc_is_payg": snap.is_payg,
        "alloc_external_stale": snap.external_sync_stale,
        "alloc_unlimited_children": [],
    }
    # L1 parents: children without a cascade ceiling count as zero (warn).
    try:
        from app.db.models import OrgPrincipal
        from app.services.org_principals import DEPTH_ONE, STATUS_ACTIVE
        from app.services.volume_allocation_cascade import cascade_warn_items_for_parent
        from sqlalchemy import select

        profile = await session.scalar(
            select(ResellerProfile).where(ResellerProfile.user_id == int(shop_id))
        )
        if profile is not None:
            principal = await session.scalar(
                select(OrgPrincipal).where(
                    OrgPrincipal.reseller_profile_id == int(profile.id),
                    OrgPrincipal.depth == DEPTH_ONE,
                    OrgPrincipal.status == STATUS_ACTIVE,
                )
            )
            if principal is not None:
                view["alloc_unlimited_children"] = await cascade_warn_items_for_parent(
                    session, int(principal.id)
                )
    except Exception:
        import logging
        logging.getLogger(__name__).debug("unlimited children warn failed", exc_info=True)
    return view


async def sync_reseller_capacity(session: AsyncSession, profile: ResellerProfile) -> tuple[int, int]:
    """Set the recorded base capacity of a «ظرفیت فعلی» reseller to the admin's live limits.

    Extras bought later are kept. Raises ``ValueError`` (safe Persian text) when there is nothing to
    sync or the panel cannot be read; nothing is written to the panel.
    """
    username = (profile.pg_admin_username or "").strip()
    if not username:
        raise ValueError(NO_PG_ADMIN)
    sub = await get_subscription(session, username)
    if sub is None:
        raise ValueError(NO_SUBSCRIPTION)
    plan = await session.get(ResellerPlan, int(sub.plan_id)) if sub.plan_id else None
    if not is_current_capacity_plan(plan):
        raise ValueError(NOT_CURRENT_CAPACITY)
    try:
        gb, users = await read_live_pg_admin_capacity(username)
    except PgCapacityUnreadable:
        await session.rollback()
        raise
    sub.base_gb, sub.base_users = gb, users
    await session.commit()
    return gb, users
