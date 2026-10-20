"""Sync volume allocated to PasarGuard users that are not local UserService rows.

Total shop allocation = local SUM(UserService) + ``ResellerProfile.external_allocated_bytes``.
A stale or failed sync never opens the gate: the last known external total is kept.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PgAdminSubscription, ResellerProfile, UserService
from app.services.billing import GB, BILLING_MODE_PAYG
from app.py_compat import timeout as asyncio_timeout

logger = logging.getLogger(__name__)

SETTING_SYNC_MINUTES = "volume_external_sync_minutes"
DEFAULT_SYNC_MINUTES = 15
STALE_PERIODS = 2
PAGE_SIZE = 200
MAX_OFFSET = 50_000
SYNC_TIMEOUT_SECONDS = 60.0
DEFAULT_CONCURRENCY = 3


@dataclass(frozen=True, slots=True)
class ExternalSyncResult:
    shop_id: int
    external_bytes: int
    panel_user_count: int
    unmatched_count: int
    ceiling_mismatch_bytes: int | None
    stale: bool
    error: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def get_external_sync_minutes(session: AsyncSession) -> int:
    from app.services.users import get_setting

    raw = await get_setting(session, SETTING_SYNC_MINUTES, str(DEFAULT_SYNC_MINUTES))
    mins = _as_int(raw, DEFAULT_SYNC_MINUTES)
    return max(1, min(1440, mins))


def external_sync_is_stale(
    synced_at: datetime | None, *, period_minutes: int, now: datetime | None = None
) -> bool:
    if synced_at is None:
        return True
    now = now or _utcnow()
    if synced_at.tzinfo is None:
        synced_at = synced_at.replace(tzinfo=timezone.utc)
    return now - synced_at > timedelta(minutes=int(period_minutes) * STALE_PERIODS)


def panel_user_limit_bytes(user: dict[str, Any]) -> int:
    """Positive finite data_limit only; 0 / missing = unlimited → counts as zero."""
    raw = user.get("data_limit")
    if raw is None:
        return 0
    n = _as_int(raw, 0)
    return n if n > 0 else 0


async def list_panel_users_for_admin(
    pg: Any, admin_username: str, *, page_size: int = PAGE_SIZE
) -> list[dict[str, Any]]:
    """Paginated panel users owned by ``admin_username`` (one batch call per page)."""
    out: list[dict[str, Any]] = []
    offset = 0
    uname = (admin_username or "").strip()
    if not uname:
        return out
    while True:
        data = await pg.get_users(admin=uname, limit=page_size, offset=offset)
        users: list[Any]
        if isinstance(data, dict):
            users = data.get("users") or data.get("items") or []
        elif isinstance(data, list):
            users = data
        else:
            users = []
        if not isinstance(users, list) or not users:
            break
        for row in users:
            if isinstance(row, dict):
                out.append(row)
        if len(users) < page_size:
            break
        offset += page_size
        if offset > MAX_OFFSET:
            break
    return out


async def compute_external_bytes(
    session: AsyncSession,
    *,
    shop_id: int,
    panel_users: list[dict[str, Any]],
) -> tuple[int, int]:
    """Return (external_bytes, unmatched_count) for panel users not in UserService."""
    if not panel_users:
        return 0, 0
    ids: list[int] = []
    names: list[str] = []
    for row in panel_users:
        uid = row.get("id")
        try:
            ids.append(int(uid))
        except (TypeError, ValueError):
            pass
        uname = str(row.get("username") or "").strip().lower()
        if uname:
            names.append(uname)
    local_ids: set[int] = set()
    local_names: set[str] = set()
    if ids:
        rows = (
            await session.execute(
                select(UserService.pg_user_id, UserService.pg_username).where(
                    UserService.shop_id == int(shop_id),
                    UserService.is_cancelled.is_(False),
                    UserService.pg_user_id.in_(ids),
                )
            )
        ).all()
        for pg_uid, pg_name in rows:
            if pg_uid is not None:
                local_ids.add(int(pg_uid))
            if pg_name:
                local_names.add(str(pg_name).strip().lower())
    if names:
        # Also match by username when pg_user_id was never synced.
        name_rows = (
            await session.execute(
                select(func.lower(UserService.pg_username)).where(
                    UserService.shop_id == int(shop_id),
                    UserService.is_cancelled.is_(False),
                    func.lower(UserService.pg_username).in_(names),
                )
            )
        ).scalars().all()
        local_names.update(str(n).strip().lower() for n in name_rows if n)
    external = 0
    unmatched = 0
    for row in panel_users:
        uid = row.get("id")
        try:
            uid_i = int(uid)
        except (TypeError, ValueError):
            uid_i = None
        uname = str(row.get("username") or "").strip().lower()
        if (uid_i is not None and uid_i in local_ids) or (uname and uname in local_names):
            continue
        unmatched += 1
        external += panel_user_limit_bytes(row)
    return int(external), int(unmatched)


async def read_panel_admin_data_limit(pg: Any, admin_username: str) -> int | None:
    """Live admin data_limit in bytes, or None when unreadable / unlimited."""
    try:
        admin = await pg.get_admin((admin_username or "").strip())
    except Exception:
        logger.debug("external sync: get_admin failed", exc_info=True)
        return None
    if not isinstance(admin, dict):
        return None
    n = _as_int(admin.get("data_limit"), 0)
    return n if n > 0 else None


async def sync_shop_external_allocation(
    session: AsyncSession,
    profile: ResellerProfile,
    *,
    pg: Any | None = None,
) -> ExternalSyncResult:
    """Refresh external allocation for one shop. On panel failure keep the previous total."""
    shop_id = int(profile.user_id)
    uname = (profile.pg_admin_username or "").strip()
    period = await get_external_sync_minutes(session)
    stale_before = external_sync_is_stale(
        getattr(profile, "external_alloc_synced_at", None), period_minutes=period
    )
    if not uname:
        return ExternalSyncResult(
            shop_id=shop_id,
            external_bytes=int(getattr(profile, "external_allocated_bytes", 0) or 0),
            panel_user_count=0,
            unmatched_count=0,
            ceiling_mismatch_bytes=None,
            stale=True,
            error="no_pg_admin",
        )
    if pg is None:
        from app.services.pasarguard import get_pg_for_reseller

        try:
            pg = await get_pg_for_reseller(session, shop_id)
        except Exception as exc:
            logger.warning(
                "external volume sync: client failed shop=%s", shop_id, exc_info=True
            )
            return ExternalSyncResult(
                shop_id=shop_id,
                external_bytes=int(getattr(profile, "external_allocated_bytes", 0) or 0),
                panel_user_count=0,
                unmatched_count=0,
                ceiling_mismatch_bytes=None,
                stale=True,
                error=str(exc)[:120],
            )
    try:
        async with asyncio_timeout(SYNC_TIMEOUT_SECONDS):
            panel_users = await list_panel_users_for_admin(pg, uname)
            external, unmatched = await compute_external_bytes(
                session, shop_id=shop_id, panel_users=panel_users
            )
            live_admin = await read_panel_admin_data_limit(pg, uname)
    except Exception as exc:
        logger.warning(
            "external volume sync failed shop=%s — keeping previous total",
            shop_id,
            exc_info=True,
        )
        return ExternalSyncResult(
            shop_id=shop_id,
            external_bytes=int(getattr(profile, "external_allocated_bytes", 0) or 0),
            panel_user_count=0,
            unmatched_count=0,
            ceiling_mismatch_bytes=None,
            stale=True,
            error=str(exc)[:120],
        )

    profile.external_allocated_bytes = int(external)
    profile.external_alloc_synced_at = _utcnow()

    ceiling_mismatch: int | None = None
    sub = await session.scalar(
        select(PgAdminSubscription).where(PgAdminSubscription.pg_username == uname)
    )
    if sub is not None and live_admin is not None:
        local_ceiling = (
            int(sub.base_gb or 0) + int(sub.extra_gb_purchased or 0)
        ) * int(GB)
        if local_ceiling > 0 and live_admin != local_ceiling:
            ceiling_mismatch = int(live_admin) - int(local_ceiling)
            logger.warning(
                "volume ceiling mismatch shop=%s admin=%s panel=%s local=%s delta=%s",
                shop_id,
                uname,
                live_admin,
                local_ceiling,
                ceiling_mismatch,
            )

    return ExternalSyncResult(
        shop_id=shop_id,
        external_bytes=int(external),
        panel_user_count=len(panel_users),
        unmatched_count=unmatched,
        ceiling_mismatch_bytes=ceiling_mismatch,
        stale=False,
        error=None,
    )


async def shops_needing_external_sync(
    session: AsyncSession, *, limit: int = 200
) -> list[ResellerProfile]:
    """Fixed-plan shops with oversell off that are due for an external sync."""
    period = await get_external_sync_minutes(session)
    cutoff = _utcnow() - timedelta(minutes=period)
    profiles = list(
        (
            await session.execute(
                select(ResellerProfile)
                .where(
                    ResellerProfile.is_active.is_(True),
                    ResellerProfile.billing_mode != BILLING_MODE_PAYG,
                    ResellerProfile.pg_admin_username.is_not(None),
                    ResellerProfile.allow_volume_oversell.is_(False),
                )
                .order_by(ResellerProfile.id.asc())
                .limit(int(limit) * 2)
            )
        ).scalars().all()
    )
    due: list[ResellerProfile] = []
    for profile in profiles:
        synced = getattr(profile, "external_alloc_synced_at", None)
        if synced is not None and synced.tzinfo is None:
            synced = synced.replace(tzinfo=timezone.utc)
        if synced is None or synced <= cutoff:
            due.append(profile)
        if len(due) >= int(limit):
            break
    return due


async def run_external_allocation_sync(
    session: AsyncSession,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    pg_factory: Any | None = None,
) -> list[ExternalSyncResult]:
    """Sync every gated shop; one bad shop must not stop the rest."""
    import asyncio

    profiles = await shops_needing_external_sync(session)
    if not profiles:
        return []
    gate = asyncio.Semaphore(max(1, int(concurrency)))
    results: list[ExternalSyncResult] = []

    async def _one(profile: ResellerProfile) -> ExternalSyncResult:
        async with gate:
            try:
                # Re-load in this session context after concurrent work.
                row = await session.get(ResellerProfile, int(profile.id))
                if row is None:
                    return ExternalSyncResult(
                        shop_id=int(profile.user_id),
                        external_bytes=0,
                        panel_user_count=0,
                        unmatched_count=0,
                        ceiling_mismatch_bytes=None,
                        stale=True,
                        error="missing",
                    )
                pg = None
                if pg_factory is not None:
                    pg = await pg_factory(session, int(row.user_id))
                return await sync_shop_external_allocation(session, row, pg=pg)
            except Exception as exc:
                logger.exception(
                    "external volume sync crashed shop=%s", getattr(profile, "user_id", None)
                )
                return ExternalSyncResult(
                    shop_id=int(getattr(profile, "user_id", 0) or 0),
                    external_bytes=int(getattr(profile, "external_allocated_bytes", 0) or 0),
                    panel_user_count=0,
                    unmatched_count=0,
                    ceiling_mismatch_bytes=None,
                    stale=True,
                    error=str(exc)[:120],
                )

    # Sequential gather under semaphore — avoid N+1 by loading profiles once above.
    for profile in profiles:
        results.append(await _one(profile))
    await session.commit()
    return results
