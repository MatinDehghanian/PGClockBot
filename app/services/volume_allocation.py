"""Volume allocation gate for fixed-plan reseller shops.

Ceiling comes from ``PgAdminSubscription`` (base_gb + extra_gb_purchased).
Allocated volume is the SQL sum of non-cancelled ``UserService.quota_data_limit_bytes``
scoped by ``shop_id``. Unlimited (0 + synced) and unsynced (NULL) count as zero and
are listed as warnings. PAYG shops are exempt. When ``allow_volume_oversell`` is on,
the gate is a no-op.

Reservation is the service row itself (``quota_status=creating`` with the intended
bytes). No separate ledger. Callers: lock → check → reserve/update → commit → panel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BotUser,
    PgAdminSubscription,
    ResellerProfile,
    UserService,
    WalletTransaction,
)
from app.services.billing import GB, BILLING_MODE_PAYG, is_payg

logger = logging.getLogger(__name__)

QUOTA_STATUS_CREATING = "creating"
QUOTA_STATUS_REVIEW = "review"

CUSTOMER_UNAVAILABLE_MSG = "فعلاً موجود نیست"
CEILING_UNKNOWN_MSG = "سقف حجم این نماینده مشخص نیست"
UNLIMITED_BLOCKED_MSG = "ساخت یا تبدیل به سرویس نامحدود وقتی فروش بیش از سقف خاموش است مجاز نیست"

Audience = Literal["admin", "customer"]


class VolumeAllocationError(Exception):
    """Expected volume-budget rejection; routes translate ``message`` for the audience."""

    def __init__(
        self,
        message: str,
        *,
        allocated_bytes: int | None = None,
        ceiling_bytes: int | None = None,
        for_customer: bool = False,
    ) -> None:
        self.message = message
        self.allocated_bytes = allocated_bytes
        self.ceiling_bytes = ceiling_bytes
        self.for_customer = for_customer
        super().__init__(message)

    def user_message(self) -> str:
        if self.for_customer:
            return CUSTOMER_UNAVAILABLE_MSG
        return self.message


@dataclass(frozen=True, slots=True)
class AllocationSnapshot:
    shop_id: int
    allocated_bytes: int
    ceiling_bytes: int | None
    allow_oversell: bool
    is_payg: bool
    expired_held_bytes: int
    unlimited_services: list[dict[str, Any]]
    is_oversold: bool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def bytes_toward_allocation(limit_bytes: int | None, *, synced: bool) -> int:
    """Bytes that count against the shop ceiling.

    NULL (never synced) and 0 with a sync stamp (unlimited) count as zero.
    Positive limits always count, including expired non-cancelled services.
    """
    if limit_bytes is None:
        return 0
    try:
        n = int(limit_bytes)
    except (TypeError, ValueError):
        return 0
    if n <= 0:
        return 0
    if not synced and n <= 0:
        return 0
    return n


def format_allocation_full_message(*, allocated_bytes: int, ceiling_bytes: int) -> str:
    """Admin/reseller-facing full message (never shown to end customers)."""
    from app.services.formatting import format_bytes

    return (
        f"سقف حجم پر است: {format_bytes(allocated_bytes)} از {format_bytes(ceiling_bytes)}"
    )


def _gate_message(
    *,
    allocated_bytes: int,
    ceiling_bytes: int,
    audience: Audience,
) -> str:
    if audience == "customer":
        return CUSTOMER_UNAVAILABLE_MSG
    return format_allocation_full_message(
        allocated_bytes=allocated_bytes, ceiling_bytes=ceiling_bytes
    )


async def lock_reseller_profile(
    session: AsyncSession, shop_id: int
) -> ResellerProfile | None:
    """Row-lock the shop profile (FOR UPDATE on PostgreSQL; SQLite serializes writers)."""
    return await session.scalar(
        select(ResellerProfile)
        .where(ResellerProfile.user_id == int(shop_id))
        .with_for_update()
    )


async def ceiling_bytes_for_profile(
    session: AsyncSession, profile: ResellerProfile
) -> int | None:
    """Return ceiling in bytes, or None when unknown (fail closed).

    PAYG is signaled by the caller via ``is_payg``; this still returns the
    subscription total when present so the capacity page can show numbers.
    """
    uname = (profile.pg_admin_username or "").strip()
    if not uname:
        return None
    sub = await session.scalar(
        select(PgAdminSubscription).where(PgAdminSubscription.pg_username == uname)
    )
    if sub is None:
        return None
    total_gb = int(sub.base_gb or 0) + int(sub.extra_gb_purchased or 0)
    if total_gb <= 0:
        # Zero means unlimited on the subscription clock — unknown for our gate.
        return None
    return int(total_gb) * int(GB)


async def sum_allocated_bytes(session: AsyncSession, shop_id: int) -> int:
    """SQL aggregate of counted volume for non-cancelled services of this shop."""
    # Positive limits only; NULL and 0 do not add. Cancelled rows are excluded.
    total = await session.scalar(
        select(func.coalesce(func.sum(UserService.quota_data_limit_bytes), 0)).where(
            UserService.shop_id == int(shop_id),
            UserService.is_cancelled.is_(False),
            UserService.quota_data_limit_bytes.is_not(None),
            UserService.quota_data_limit_bytes > 0,
        )
    )
    return int(total or 0)


async def sum_expired_held_bytes(session: AsyncSession, shop_id: int) -> int:
    """Volume still held by expired (but not cancelled) services."""
    now = _utcnow()
    total = await session.scalar(
        select(func.coalesce(func.sum(UserService.quota_data_limit_bytes), 0)).where(
            UserService.shop_id == int(shop_id),
            UserService.is_cancelled.is_(False),
            UserService.quota_data_limit_bytes.is_not(None),
            UserService.quota_data_limit_bytes > 0,
            UserService.quota_expire_at.is_not(None),
            UserService.quota_expire_at < now,
        )
    )
    return int(total or 0)


async def list_unlimited_or_unsynced_services(
    session: AsyncSession, shop_id: int, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Services that count as zero and should be warned about on the capacity page."""
    rows = (
        await session.execute(
            select(UserService)
            .where(
                UserService.shop_id == int(shop_id),
                UserService.is_cancelled.is_(False),
                or_(
                    UserService.quota_data_limit_bytes.is_(None),
                    UserService.quota_data_limit_bytes == 0,
                ),
            )
            .order_by(UserService.id.desc())
            .limit(int(limit))
        )
    ).scalars().all()
    out: list[dict[str, Any]] = []
    for svc in rows:
        synced = getattr(svc, "quota_synced_at", None) is not None
        limit_b = getattr(svc, "quota_data_limit_bytes", None)
        kind = "unsynced" if limit_b is None else "unlimited"
        out.append(
            {
                "id": int(svc.id),
                "pg_username": str(svc.pg_username or ""),
                "kind": kind,
                "synced": synced,
            }
        )
    return out


async def build_allocation_snapshot(
    session: AsyncSession, shop_id: int
) -> AllocationSnapshot | None:
    profile = await session.scalar(
        select(ResellerProfile).where(ResellerProfile.user_id == int(shop_id))
    )
    if profile is None:
        return None
    payg = is_payg(profile)
    ceiling = await ceiling_bytes_for_profile(session, profile)
    allocated = await sum_allocated_bytes(session, shop_id)
    expired_held = await sum_expired_held_bytes(session, shop_id)
    unlimited = await list_unlimited_or_unsynced_services(session, shop_id)
    allow = bool(getattr(profile, "allow_volume_oversell", True))
    oversold = (
        (not payg)
        and (not allow)
        and ceiling is not None
        and allocated > ceiling
    )
    return AllocationSnapshot(
        shop_id=int(shop_id),
        allocated_bytes=allocated,
        ceiling_bytes=ceiling,
        allow_oversell=allow,
        is_payg=payg,
        expired_held_bytes=expired_held,
        unlimited_services=unlimited,
        is_oversold=oversold,
    )


async def list_oversold_shop_ids(
    session: AsyncSession, *, limit: int = 200
) -> list[int]:
    """Shop ids whose local allocation exceeds their fixed-plan ceiling (Owner dashboard)."""
    profiles = (
        await session.execute(
            select(ResellerProfile).where(
                ResellerProfile.is_active.is_(True),
                ResellerProfile.allow_volume_oversell.is_(False),
                ResellerProfile.billing_mode != BILLING_MODE_PAYG,
                ResellerProfile.pg_admin_username.is_not(None),
            ).limit(int(limit))
        )
    ).scalars().all()
    if not profiles:
        return []
    unames = [str(p.pg_admin_username).strip() for p in profiles if p.pg_admin_username]
    subs = (
        await session.execute(
            select(PgAdminSubscription).where(PgAdminSubscription.pg_username.in_(unames))
        )
    ).scalars().all()
    ceiling_by_uname = {
        str(s.pg_username): (int(s.base_gb or 0) + int(s.extra_gb_purchased or 0)) * int(GB)
        for s in subs
        if (int(s.base_gb or 0) + int(s.extra_gb_purchased or 0)) > 0
    }
    shop_ids = [int(p.user_id) for p in profiles]
    sums = (
        await session.execute(
            select(
                UserService.shop_id,
                func.coalesce(func.sum(UserService.quota_data_limit_bytes), 0),
            )
            .where(
                UserService.shop_id.in_(shop_ids),
                UserService.is_cancelled.is_(False),
                UserService.quota_data_limit_bytes.is_not(None),
                UserService.quota_data_limit_bytes > 0,
            )
            .group_by(UserService.shop_id)
        )
    ).all()
    allocated_by_shop = {int(sid): int(total or 0) for sid, total in sums if sid is not None}
    oversold: list[int] = []
    for profile in profiles:
        uname = (profile.pg_admin_username or "").strip()
        ceiling = ceiling_by_uname.get(uname)
        if ceiling is None:
            continue
        if allocated_by_shop.get(int(profile.user_id), 0) > ceiling:
            oversold.append(int(profile.user_id))
    return oversold


async def assert_volume_delta_allowed(
    session: AsyncSession,
    *,
    shop_id: int | None,
    delta_bytes: int | None,
    audience: Audience = "admin",
    lock: bool = True,
    allow_unlimited: bool = False,
) -> None:
    """Raise ``VolumeAllocationError`` when a positive delta would exceed the ceiling.

    ``delta_bytes`` None means the intended limit is unknown → fail closed when gated.
    ``delta_bytes`` 0 with ``allow_unlimited=False`` rejects unlimited create/convert.
    Negative or zero deltas (shrink / delete) always pass.
    """
    if shop_id is None:
        return
    sid = int(shop_id)

    if delta_bytes is not None:
        try:
            delta = int(delta_bytes)
        except (TypeError, ValueError) as exc:
            raise VolumeAllocationError(
                CEILING_UNKNOWN_MSG if audience == "admin" else CUSTOMER_UNAVAILABLE_MSG,
                for_customer=(audience == "customer"),
            ) from exc
    else:
        delta = None

    profile = (
        await lock_reseller_profile(session, sid)
        if lock
        else await session.scalar(
            select(ResellerProfile).where(ResellerProfile.user_id == sid)
        )
    )
    if profile is None:
        return
    if is_payg(profile):
        return
    if bool(getattr(profile, "allow_volume_oversell", True)):
        return

    if delta is None:
        raise VolumeAllocationError(
            CEILING_UNKNOWN_MSG if audience == "admin" else CUSTOMER_UNAVAILABLE_MSG,
            for_customer=(audience == "customer"),
        )
    if delta == 0 and not allow_unlimited:
        raise VolumeAllocationError(
            UNLIMITED_BLOCKED_MSG if audience == "admin" else CUSTOMER_UNAVAILABLE_MSG,
            for_customer=(audience == "customer"),
        )
    if delta <= 0:
        return

    ceiling = await ceiling_bytes_for_profile(session, profile)
    if ceiling is None:
        raise VolumeAllocationError(
            CEILING_UNKNOWN_MSG if audience == "admin" else CUSTOMER_UNAVAILABLE_MSG,
            for_customer=(audience == "customer"),
        )

    allocated = await sum_allocated_bytes(session, sid)
    if allocated + delta > ceiling:
        raise VolumeAllocationError(
            _gate_message(
                allocated_bytes=allocated, ceiling_bytes=ceiling, audience=audience
            ),
            allocated_bytes=allocated,
            ceiling_bytes=ceiling,
            for_customer=(audience == "customer"),
        )


async def assert_new_limit_allowed(
    session: AsyncSession,
    *,
    shop_id: int | None,
    current_limit_bytes: int | None,
    new_limit_bytes: int | None,
    audience: Audience = "admin",
    lock: bool = True,
) -> None:
    """Gate an absolute limit change using the positive delta only."""
    if shop_id is None:
        return
    if new_limit_bytes is None:
        await assert_volume_delta_allowed(
            session,
            shop_id=shop_id,
            delta_bytes=None,
            audience=audience,
            lock=lock,
        )
        return
    try:
        new_b = int(new_limit_bytes)
    except (TypeError, ValueError) as exc:
        raise VolumeAllocationError(
            CEILING_UNKNOWN_MSG if audience == "admin" else CUSTOMER_UNAVAILABLE_MSG,
            for_customer=(audience == "customer"),
        ) from exc
    if new_b == 0:
        await assert_volume_delta_allowed(
            session,
            shop_id=shop_id,
            delta_bytes=0,
            audience=audience,
            lock=lock,
            allow_unlimited=False,
        )
        return
    cur = bytes_toward_allocation(
        current_limit_bytes,
        synced=current_limit_bytes is not None,
    )
    delta = max(0, new_b - cur)
    await assert_volume_delta_allowed(
        session,
        shop_id=shop_id,
        delta_bytes=delta,
        audience=audience,
        lock=lock,
        allow_unlimited=True,
    )


def is_hard_panel_rejection(exc: BaseException) -> bool:
    """True when the panel definitely refused the mutation (safe to release reservation)."""
    from app.services.pasarguard import PasarGuardError

    return isinstance(exc, PasarGuardError) and exc.status_code in (
        400,
        401,
        403,
        404,
        409,
        422,
    )


async def reserve_creating_service(
    session: AsyncSession,
    *,
    bot_user_id: int,
    shop_id: int,
    plan_id: int | None,
    pg_username: str,
    data_limit_bytes: int,
    remark: str,
    expire_at: datetime | None = None,
) -> UserService:
    """Insert a creating-row reservation that counts toward allocation immediately."""
    service = UserService(
        bot_user_id=int(bot_user_id),
        plan_id=plan_id,
        pg_username=str(pg_username)[:128],
        remark=remark[:255] if remark else None,
        shop_id=int(shop_id),
        quota_data_limit_bytes=int(data_limit_bytes),
        quota_expire_at=expire_at,
        quota_synced_at=_utcnow(),
        quota_status=QUOTA_STATUS_CREATING,
    )
    session.add(service)
    await session.flush()
    return service


async def release_creating_service(session: AsyncSession, service: UserService) -> None:
    """Drop a creating reservation after a definitive panel failure."""
    if getattr(service, "quota_status", None) != QUOTA_STATUS_CREATING:
        return
    await session.delete(service)
    await session.flush()


async def mark_service_review(session: AsyncSession, service: UserService) -> None:
    """Keep the reservation and flag the row for operator review (unknown panel outcome)."""
    service.quota_status = QUOTA_STATUS_REVIEW
    service.shop_needs_review = True
    await session.flush()


async def finalize_creating_service(
    session: AsyncSession,
    service: UserService,
    *,
    pg_user_id: int | None,
    pg_username: str,
    subscription_url: str | None,
    subscription_token: str | None,
    quota_status: str | None = "active",
) -> None:
    service.pg_user_id = int(pg_user_id) if pg_user_id is not None else None
    service.pg_username = str(pg_username)[:128]
    service.subscription_url = subscription_url
    service.subscription_token = subscription_token
    service.quota_status = (quota_status or "active")[:32]
    service.shop_needs_review = False
    await session.flush()


async def refund_volume_gate_once(
    session: AsyncSession,
    *,
    user: BotUser,
    amount: int,
    order_id: int,
    shop_id: int | None,
) -> bool:
    """Idempotent wallet credit when delivery is rejected by the volume gate.

    Returns True when a new credit was written. Uses a unique reason string and
    checks the ledger before crediting so a double call cannot mint money twice.
    """
    if amount <= 0:
        return False
    reason = f"volume_gate_refund:order:{int(order_id)}"
    existing = await session.scalar(
        select(WalletTransaction.id).where(
            WalletTransaction.user_id == int(user.id),
            WalletTransaction.reason == reason,
        ).limit(1)
    )
    if existing is not None:
        return False
    from app.services.wallet import credit_wallet

    await credit_wallet(
        session,
        user,
        int(amount),
        reason,
        shop_id=shop_id,
        commit=False,
    )
    return True


async def set_allow_volume_oversell(
    session: AsyncSession,
    profile: ResellerProfile,
    *,
    allow: bool,
    actor_is_owner: bool,
) -> None:
    """Only the platform Owner may change the oversell switch."""
    if not actor_is_owner:
        raise VolumeAllocationError("فقط مالک سیستم می‌تواند فروش بیش از سقف حجم را تغییر دهد")
    profile.allow_volume_oversell = bool(allow)


async def maybe_warn_volume_thresholds(
    session: AsyncSession,
    *,
    shop_id: int,
) -> list[Any]:
    """Build panel-alert signals for 80% and 100% allocation (once per threshold).

    Reuses ``PanelAlertState`` / ``claim_signal``. Callers send via the existing
    notification dispatch. Returns zero, one or two ``Signal`` objects.
    """
    from app.services.panel_alert_notifications import Signal

    snap = await build_allocation_snapshot(session, shop_id)
    if snap is None or snap.is_payg or snap.allow_oversell or snap.ceiling_bytes is None:
        return []
    if snap.ceiling_bytes <= 0:
        return []
    pct = (100.0 * snap.allocated_bytes) / float(snap.ceiling_bytes)
    from app.services.formatting import format_bytes

    signals: list[Signal] = []
    if pct >= 100.0:
        signals.append(
            Signal(
                shop_id=int(shop_id),
                alert="volume_alloc_100",
                notify_key="notify_panel_capacity",
                count=1,
                text=(
                    "⛔ سقف تخصیص حجم فروشگاه پر شد "
                    f"({format_bytes(snap.allocated_bytes)} از {format_bytes(snap.ceiling_bytes)})."
                ),
                path="/resellers",
                fingerprint="100",
            )
        )
    elif pct >= 80.0:
        signals.append(
            Signal(
                shop_id=int(shop_id),
                alert="volume_alloc_80",
                notify_key="notify_panel_capacity",
                count=1,
                text=(
                    "⚠️ تخصیص حجم فروشگاه به ۸۰٪ سقف رسید "
                    f"({format_bytes(snap.allocated_bytes)} از {format_bytes(snap.ceiling_bytes)})."
                ),
                path="/resellers",
                fingerprint="80",
            )
        )
    return signals
