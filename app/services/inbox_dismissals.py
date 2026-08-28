"""Persisted dismiss/snooze for computed panel inbox alerts."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PanelInboxDismissal

logger = logging.getLogger(__name__)

MODE_24H = "24h"
MODE_FOREVER = "forever"
SNOOZE_HOURS = 24

ALLOWED_ALERT_KEYS = frozenset(
    {
        "update",
        "ticket_alert",
        "shop_maintenance",
        "capacity_warn",
        "payg_suspended",
        "payg_low",
        "ac:pending",
        "ac:delivery",
        "ac:tickets",
        "ac:expiring",
        "ac:low_volume",
    }
)


def staff_dismiss_key(staff: dict) -> str:
    role = str(staff.get("role") or "")
    uid = staff.get("bot_user_id") or staff.get("id") or staff.get("username") or ""
    return f"{role}:{uid}"[:128]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def alert_key_for_action_center(entry_key: str) -> str:
    return f"ac:{entry_key}"


def is_dismissed(
    row: PanelInboxDismissal,
    *,
    alert_active: bool,
    now: datetime | None = None,
) -> bool:
    """Return True when the alert should stay hidden."""
    now = now or _utcnow()
    dismissed_at = _aware(row.dismissed_at)
    if row.mode == MODE_24H:
        return now < dismissed_at + timedelta(hours=SNOOZE_HOURS)
    # forever: hide while the underlying condition is still active
    if row.mode == MODE_FOREVER:
        return bool(alert_active)
    return False


async def upsert_dismissal(
    session: AsyncSession,
    *,
    staff: dict,
    alert_key: str,
    mode: str,
    entity_id: str = "",
) -> None:
    key = staff_dismiss_key(staff)
    alert_key = (alert_key or "").strip()
    if alert_key not in ALLOWED_ALERT_KEYS:
        raise ValueError("اعلان نامعتبر")
    if mode not in (MODE_24H, MODE_FOREVER):
        raise ValueError("حالت حذف نامعتبر")
    entity_id = (entity_id or "").strip()[:64]

    existing = (
        await session.execute(
            select(PanelInboxDismissal).where(
                PanelInboxDismissal.staff_key == key,
                PanelInboxDismissal.alert_key == alert_key,
                PanelInboxDismissal.entity_id == entity_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.mode = mode
        existing.dismissed_at = _utcnow()
    else:
        session.add(
            PanelInboxDismissal(
                staff_key=key,
                alert_key=alert_key,
                entity_id=entity_id,
                mode=mode,
                dismissed_at=_utcnow(),
            )
        )
    await session.commit()


async def load_dismissals(
    session: AsyncSession,
    staff: dict,
) -> list[PanelInboxDismissal]:
    key = staff_dismiss_key(staff)
    return list(
        (
            await session.execute(
                select(PanelInboxDismissal).where(PanelInboxDismissal.staff_key == key)
            )
        )
        .scalars()
        .all()
    )


def _action_center_active_keys(ac: dict[str, Any]) -> dict[str, bool]:
    """Map action-center alert keys from counts (not only rendered entries)."""
    out: dict[str, bool] = {}
    if int(ac.get("pending") or 0) > 0:
        out["ac:pending"] = True
    if int(ac.get("failures") or 0) > 0:
        out["ac:delivery"] = True
    if int(ac.get("tickets") or 0) > 0:
        out["ac:tickets"] = True
    if int(ac.get("expiring") or 0) > 0:
        out["ac:expiring"] = True
    if int(ac.get("low_volume") or 0) > 0:
        out["ac:low_volume"] = True
    for entry in ac.get("entries") or []:
        ek = str(entry.get("key") or "")
        if ek:
            out[alert_key_for_action_center(ek)] = True
    return out


def _alert_active_map(ctx: dict[str, Any]) -> dict[str, bool]:
    """Which alert keys are currently active in a built inbox context."""
    pr = ctx.get("payg_risk") or {}
    active: dict[str, bool] = {
        "update": bool((ctx.get("update") or {}).get("update_available")),
        "shop_maintenance": bool(ctx.get("shop_maintenance")),
        "capacity_warn": bool(ctx.get("capacity_warn")),
        "payg_suspended": bool(pr.get("suspended")),
        "payg_low": bool(pr.get("low")),
    }
    ta = ctx.get("ticket_alert")
    if ta:
        active["ticket_alert"] = True
    if ctx.get("action_center_ok", True):
        active.update(_action_center_active_keys(ctx.get("action_center") or {}))
    return active


async def cleanup_resolved_dismissals(
    session: AsyncSession,
    staff: dict,
    ctx: dict[str, Any],
) -> None:
    """Drop forever-dismiss rows once their alert is no longer active."""
    if not ctx.get("action_center_ok", True):
        return
    rows = await load_dismissals(session, staff)
    if not rows:
        return

    active = _alert_active_map(ctx)

    stale_ids: list[int] = []
    for row in rows:
        if row.mode != MODE_FOREVER:
            continue
        if row.alert_key == "ticket_alert":
            ta = ctx.get("ticket_alert")
            if not ta:
                stale_ids.append(int(row.id))
                continue
            if row.entity_id:
                eid = str(ta.get("ticket_id") or ta.get("id") or "")
                if eid != row.entity_id:
                    stale_ids.append(int(row.id))
            continue
        if not active.get(row.alert_key, False):
            stale_ids.append(int(row.id))
    if stale_ids:
        await session.execute(
            delete(PanelInboxDismissal).where(PanelInboxDismissal.id.in_(stale_ids))
        )
        await session.commit()


async def clear_staff_dismissals(session: AsyncSession, staff: dict) -> int:
    """Remove all persisted hide/snooze rows for this staff member."""
    key = staff_dismiss_key(staff)
    result = await session.execute(
        delete(PanelInboxDismissal).where(PanelInboxDismissal.staff_key == key)
    )
    await session.commit()
    return int(result.rowcount or 0)


def _row_matches(row: PanelInboxDismissal, alert_key: str, entity_id: str = "") -> bool:
    if row.alert_key != alert_key:
        return False
    if row.entity_id and entity_id and row.entity_id != entity_id:
        return False
    if row.entity_id and not entity_id:
        return False
    return True


async def filter_action_center_for_staff(
    session: AsyncSession,
    staff: dict,
    action_center: dict[str, Any],
) -> dict[str, Any]:
    """Apply persisted dismissals to a dashboard work-queue payload."""
    dismissals = await load_dismissals(session, staff)
    if not dismissals:
        return action_center
    filtered = filter_inbox_context({"action_center": action_center}, dismissals)
    return filtered.get("action_center") or action_center


def filter_inbox_context(
    ctx: dict[str, Any],
    dismissals: list[PanelInboxDismissal],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply dismissals to a built inbox context (mutates copy)."""
    now = now or _utcnow()
    out = dict(ctx)

    def hidden(alert_key: str, active: bool, entity_id: str = "") -> bool:
        for row in dismissals:
            if not _row_matches(row, alert_key, entity_id):
                continue
            if is_dismissed(row, alert_active=active, now=now):
                return True
        return False

    if out.get("update") and hidden("update", bool((out["update"] or {}).get("update_available"))):
        out["update"] = dict(out["update"])
        out["update"]["update_available"] = False

    if out.get("ticket_alert"):
        ta = out["ticket_alert"]
        eid = str(ta.get("ticket_id") or ta.get("id") or "")
        if hidden("ticket_alert", True, eid):
            out["ticket_alert"] = None

    if out.get("shop_maintenance") and hidden("shop_maintenance", True):
        out["shop_maintenance"] = False

    if out.get("capacity_warn") and hidden("capacity_warn", True):
        out["capacity_warn"] = False

    pr = dict(out.get("payg_risk") or {})
    if pr.get("suspended") and hidden("payg_suspended", True):
        pr["suspended"] = []
    if pr.get("low") and hidden("payg_low", True):
        pr["low"] = []
    pr["has_items"] = bool(pr.get("suspended") or pr.get("low"))
    out["payg_risk"] = pr

    ac = dict(out.get("action_center") or {})
    entries = []
    for entry in ac.get("entries") or []:
        ek = str(entry.get("key") or "")
        ak = alert_key_for_action_center(ek)
        if hidden(ak, True):
            continue
        entries.append(entry)
    ac["entries"] = entries
    ac["has_items"] = bool(entries)
    out["action_center"] = ac

    from app.services.panel_inbox import inbox_alert_count

    out["inbox_count"] = inbox_alert_count(out)
    out["inbox_has"] = out["inbox_count"] > 0
    return out
