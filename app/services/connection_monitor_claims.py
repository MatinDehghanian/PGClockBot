"""Committed local runtime and target leases for monitoring workers."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import ConnectionMonitorState, ConnectionMonitorTarget
from app.services.connection_monitor_settings import LOCAL_PROBE_ID


MONITOR_LEASE_SECONDS = 90


@dataclass(frozen=True, slots=True)
class MonitorCycleClaim:
    state_id: int
    account_revision: str
    expires_at: datetime
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class MonitorTargetClaim:
    target_id: int
    pg_host_id: int
    generation: str
    expires_at: datetime
    cycle: MonitorCycleClaim
    token: str = field(repr=False)


def _utc(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Monitoring lease time must be timezone aware")
    return now.astimezone(timezone.utc)


def current_monitor_cycle(claim: MonitorCycleClaim, *, now: datetime) -> ColumnElement[bool]:
    return exists(select(ConnectionMonitorState.id).where(
        ConnectionMonitorState.id == claim.state_id, ConnectionMonitorState.reseller_id.is_(None),
        ConnectionMonitorState.probe_id == LOCAL_PROBE_ID, ConnectionMonitorState.enabled.is_(True),
        ConnectionMonitorState.account_revision == claim.account_revision,
        ConnectionMonitorState.cycle_token == claim.token, ConnectionMonitorState.cycle_lease_until > _utc(now),
    ))


async def claim_monitor_cycle(session: AsyncSession, *, now: datetime) -> MonitorCycleClaim | None:
    now = _utc(now)
    token, expires = secrets.token_hex(32), now + timedelta(seconds=MONITOR_LEASE_SECONDS)
    result = await session.execute(update(ConnectionMonitorState).where(
        ConnectionMonitorState.reseller_id.is_(None), ConnectionMonitorState.probe_id == LOCAL_PROBE_ID,
        ConnectionMonitorState.enabled.is_(True), ConnectionMonitorState.pg_user_id.is_not(None),
        ConnectionMonitorState.subscription_token_enc.is_not(None), ConnectionMonitorState.account_revision != "",
        or_(ConnectionMonitorState.cycle_lease_until.is_(None), ConnectionMonitorState.cycle_lease_until <= now),
    ).values(cycle_token=token, cycle_lease_until=expires).returning(
        ConnectionMonitorState.id, ConnectionMonitorState.account_revision,
    ))
    row = result.first()
    await session.commit()
    return MonitorCycleClaim(row.id, row.account_revision, expires, token) if row else None


async def release_monitor_cycle(session: AsyncSession, claim: MonitorCycleClaim) -> None:
    await session.execute(update(ConnectionMonitorState).where(
        ConnectionMonitorState.id == claim.state_id, ConnectionMonitorState.reseller_id.is_(None),
        ConnectionMonitorState.probe_id == LOCAL_PROBE_ID, ConnectionMonitorState.cycle_token == claim.token,
    ).values(cycle_token=None, cycle_lease_until=None))
    await session.commit()


async def claim_monitor_target(session: AsyncSession, cycle: MonitorCycleClaim, *, target_id: int,
                               now: datetime) -> MonitorTargetClaim | None:
    now = _utc(now)
    if type(target_id) is not int or not 1 <= target_id <= 2147483647:
        raise ValueError("Invalid monitoring target")
    token = secrets.token_hex(32)
    result = await session.execute(update(ConnectionMonitorTarget).where(
        ConnectionMonitorTarget.id == target_id, ConnectionMonitorTarget.reseller_id.is_(None),
        ConnectionMonitorTarget.test_enabled.is_(True), ConnectionMonitorTarget.generation != "",
        ConnectionMonitorTarget.endpoint_count > 0, ConnectionMonitorTarget.next_check_at <= now,
        or_(ConnectionMonitorTarget.claim_until.is_(None), ConnectionMonitorTarget.claim_until <= now),
        current_monitor_cycle(cycle, now=now),
    ).values(claim_token=token, claim_until=cycle.expires_at).returning(
        ConnectionMonitorTarget.id, ConnectionMonitorTarget.pg_host_id, ConnectionMonitorTarget.generation,
    ))
    row = result.first()
    await session.commit()
    return MonitorTargetClaim(row.id, row.pg_host_id, row.generation, cycle.expires_at, cycle, token) if row else None


async def release_monitor_target(session: AsyncSession, claim: MonitorTargetClaim) -> None:
    await session.execute(update(ConnectionMonitorTarget).where(
        ConnectionMonitorTarget.id == claim.target_id, ConnectionMonitorTarget.reseller_id.is_(None),
        ConnectionMonitorTarget.claim_token == claim.token,
    ).values(claim_token=None, claim_until=None))
    await session.commit()
