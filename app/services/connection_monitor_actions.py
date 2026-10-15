"""Resolve scoped target edits before fresh catalog validation and mutation."""

from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConnectionMonitorTarget
from app.services.connection_monitor_access import MonitorAccess, require_monitor_owner
from app.services.connection_monitor_preferences import (
    PREFERENCES_UNAVAILABLE,
    MonitorPreferences,
    save_monitor_preferences,
)


INVALID_PREFERENCES = "نام عمومی معتبر تا ۶۴ نویسه و ترتیب عددی بین صفر و ۲۱۴۷۴۸۳۶۴۷ لازم است."


async def select_monitor_host(session: AsyncSession, access: MonitorAccess, *, host_id: int) -> int:
    try:
        preferences = MonitorPreferences(host_id=host_id)
    except ValidationError:
        raise ValueError(PREFERENCES_UNAVAILABLE) from None
    await require_monitor_owner(session, access)
    target = await session.scalar(select(ConnectionMonitorTarget).where(
        ConnectionMonitorTarget.reseller_id.is_(None), ConnectionMonitorTarget.pg_host_id == host_id,
    ).limit(1))
    if target is not None:
        preferences = MonitorPreferences(host_id=host_id, public_name=target.public_name, display_order=target.display_order,
                                         is_public=target.is_public if target.test_enabled else False)
    await session.commit()
    return await save_monitor_preferences(session, access, preferences)


async def edit_monitor_target(session: AsyncSession, access: MonitorAccess, *, target_id: int,
                               field: str, value: object) -> int:
    if type(target_id) is not int or not 1 <= target_id <= 2147483647:
        raise ValueError(PREFERENCES_UNAVAILABLE)
    if field not in ("public_name", "display_order", "is_public"):
        raise ValueError(INVALID_PREFERENCES)
    await require_monitor_owner(session, access)
    target = await session.scalar(select(ConnectionMonitorTarget).where(
        ConnectionMonitorTarget.id == target_id, ConnectionMonitorTarget.reseller_id.is_(None),
        ConnectionMonitorTarget.test_enabled.is_(True),
    ).limit(1))
    if target is None:
        raise ValueError(PREFERENCES_UNAVAILABLE)
    values = {"host_id": target.pg_host_id, "public_name": target.public_name,
              "display_order": target.display_order, "is_public": target.is_public, field: value}
    await session.commit()
    try:
        preferences = MonitorPreferences.model_validate(values)
    except ValidationError:
        raise ValueError(INVALID_PREFERENCES) from None
    return await save_monitor_preferences(session, access, preferences)
