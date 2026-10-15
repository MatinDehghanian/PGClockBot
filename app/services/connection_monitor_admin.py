"""Owner runtime controls and bounded active-host choices without exposing routes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import ConnectionMonitorSnapshot, ConnectionMonitorState, ConnectionMonitorTarget
from app.services.connection_monitor_access import MonitorAccess, active_monitor_owner, require_monitor_owner
from app.services.connection_monitor_panel import read_monitor_catalog
from app.services.connection_monitor_preferences import PREFERENCES_UNAVAILABLE, owner_monitor_account
from app.services.connection_monitor_settings import ACCOUNT_UNAVAILABLE, monitor_settings, reveal_monitor_token
from app.services.connection_monitor_types import MAX_CATALOG_ITEMS
from app.services.xray_probe_resources import XrayBinary


@dataclass(frozen=True, slots=True)
class MonitorHostChoice:
    host_id: int
    name: str


@dataclass(frozen=True, slots=True)
class MonitorHostPage:
    choices: tuple[MonitorHostChoice, ...]
    next_host_id: int | None


async def active_monitor_hosts(session: AsyncSession, access: MonitorAccess, *, after_id: int = 0) -> MonitorHostPage:
    if type(after_id) is not int or not 0 <= after_id <= 2147483647:
        raise ValueError(PREFERENCES_UNAVAILABLE)
    account = await owner_monitor_account(session, access)
    catalog = await read_monitor_catalog(account)
    if not isinstance(catalog.hosts, list) or len(catalog.hosts) > MAX_CATALOG_ITEMS:
        raise ValueError(PREFERENCES_UNAVAILABLE)
    choices = []
    for host in catalog.hosts:
        if not isinstance(host, dict) or type(host.get("id")) is not int or not 1 <= host["id"] <= 2147483647:
            raise ValueError(PREFERENCES_UNAVAILABLE)
        if host["id"] > after_id and host.get("is_disabled", False) is False:
            name = host.get("remark")
            choices.append(MonitorHostChoice(host["id"], name[:64] if isinstance(name, str) and name else str(host["id"])))
    choices.sort(key=lambda item: item.host_id)
    return MonitorHostPage(tuple(choices[:10]), choices[9].host_id if len(choices) > 10 else None)


async def set_monitor_enabled(session: AsyncSession, access: MonitorAccess, *, enabled: bool) -> None:
    if type(enabled) is not bool:
        raise ValueError(PREFERENCES_UNAVAILABLE)
    settings = await monitor_settings(session, access)
    if settings.enabled is enabled:
        return
    if enabled:
        account = await owner_monitor_account(session, access)
        await reveal_monitor_token(account.encrypted_token)
        deployment = get_settings()
        binary = XrayBinary(Path(deployment.connection_monitor_xray_path), deployment.connection_monitor_xray_sha256)
        await asyncio.to_thread(binary.verify)
    result = await session.execute(update(ConnectionMonitorState).where(
        ConnectionMonitorState.id == settings.id, ConnectionMonitorState.reseller_id.is_(None), active_monitor_owner(access),
        ConnectionMonitorState.enabled.is_(not enabled),
        *([ConnectionMonitorState.account_revision == account.revision] if enabled else []),
    ).values(enabled=enabled, cycle_token=None, cycle_lease_until=None, catalog_synced_at=None))
    if result.rowcount != 1:
        await session.rollback()
        await require_monitor_owner(session, access)
        current = await session.scalar(select(ConnectionMonitorState.enabled).where(
            ConnectionMonitorState.id == settings.id, ConnectionMonitorState.reseller_id.is_(None),
        ).limit(1))
        await session.commit()
        if current is enabled:
            return
        raise ValueError(ACCOUNT_UNAVAILABLE)
    await session.execute(update(ConnectionMonitorTarget).where(ConnectionMonitorTarget.reseller_id.is_(None)).values(
        is_public=False, claim_token=None, claim_until=None, manual_pending=False,
    ))
    await session.execute(update(ConnectionMonitorSnapshot).where(ConnectionMonitorSnapshot.reseller_id.is_(None)).values(
        status="unknown", checked_at=datetime.now(timezone.utc), reason="monitor_paused" if not enabled else None,
        delay_ms=None, success_streak=0, failure_streak=0, recovery_required=ConnectionMonitorSnapshot.has_observation, samples_json="[]",
    ))
    await session.commit()
