"""Validate and save Owner host choices against a fresh supported panel catalog."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConnectionMonitorSnapshot, ConnectionMonitorState, ConnectionMonitorTarget
from app.services.connection_monitor_access import MonitorAccess, active_monitor_owner, require_monitor_owner
from app.services.connection_monitor_catalog import plan_monitor_hosts
from app.services.connection_monitor_claims import eligible_monitor_account
from app.services.connection_monitor_panel import MonitorAccount, read_monitor_catalog
from app.services.connection_monitor_settings import ACCOUNT_UNAVAILABLE, LOCAL_PROBE_ID, monitor_settings
from app.services.connection_monitor_sync import apply_target_plan, initial_snapshots
from app.services.connection_monitor_types import MAX_MONITOR_ENDPOINTS, MonitorConfigError, MonitorIssue


PREFERENCES_UNAVAILABLE = "انتخاب هاست تغییر کرده یا این هاست آمادهٔ تست نیست؛ فهرست را تازه کنید."


class MonitorPreferences(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    host_id: Annotated[int, Field(ge=1, le=2147483647)]
    public_name: Annotated[str, Field(max_length=64)] = ""
    is_public: bool = False
    display_order: Annotated[int, Field(ge=0, le=2147483647)] = 0

    @field_validator("public_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Invalid public monitoring name")
        return value

    @model_validator(mode="after")
    def require_public_name(self) -> MonitorPreferences:
        if self.is_public and not self.public_name:
            raise ValueError("A public monitoring name is required")
        return self


async def owner_monitor_account(session: AsyncSession, access: MonitorAccess) -> MonitorAccount:
    settings = await monitor_settings(session, access)
    state = await session.scalar(select(ConnectionMonitorState).where(
        ConnectionMonitorState.id == settings.id, ConnectionMonitorState.reseller_id.is_(None),
        ConnectionMonitorState.probe_id == LOCAL_PROBE_ID,
        eligible_monitor_account(),
    ).limit(1))
    if state is None or not state.pg_user_id or not state.pg_username or not state.subscription_token_enc or not state.account_revision:
        await session.rollback()
        raise ValueError(ACCOUNT_UNAVAILABLE)
    account = MonitorAccount(state.pg_user_id, state.account_revision, state.subscription_token_enc, state.pg_username)
    await session.commit()
    return account


async def save_monitor_preferences(session: AsyncSession, access: MonitorAccess, preferences: MonitorPreferences, *,
                                   expected_target_id: int | None = None) -> int:
    account = await owner_monitor_account(session, access)
    selected = tuple((await session.scalars(select(ConnectionMonitorTarget.pg_host_id).where(
        ConnectionMonitorTarget.reseller_id.is_(None), ConnectionMonitorTarget.test_enabled.is_(True),
    ).order_by(ConnectionMonitorTarget.id).limit(MAX_MONITOR_ENDPOINTS + 1))).all())
    await session.commit()
    chosen = tuple(dict.fromkeys((*selected, preferences.host_id)))
    catalog = await read_monitor_catalog(account)
    plans = await asyncio.to_thread(
        plan_monitor_hosts, hosts=catalog.hosts, inbounds=catalog.inbounds, native_configs=catalog.native_configs,
        selected_ids=chosen, staff={"pg_is_owner": True}, account_revision=account.revision,
    )
    plan = next(plan for plan in plans if plan.host_id == preferences.host_id)
    if not plan.is_ready:
        raise MonitorConfigError(plan.issue or MonitorIssue.MISSING_ROUTE)
    guard = await session.execute(update(ConnectionMonitorState).where(
        ConnectionMonitorState.reseller_id.is_(None), ConnectionMonitorState.probe_id == LOCAL_PROBE_ID,
        ConnectionMonitorState.account_revision == account.revision, active_monitor_owner(access),
        eligible_monitor_account(),
        *([ConnectionMonitorState.enabled.is_(True)] if preferences.is_public else []),
        *([exists(select(ConnectionMonitorTarget.id).where(
            ConnectionMonitorTarget.id == expected_target_id, ConnectionMonitorTarget.reseller_id.is_(None),
            ConnectionMonitorTarget.pg_host_id == preferences.host_id, ConnectionMonitorTarget.test_enabled.is_(True),
        ))] if expected_target_id is not None else []),
    ).values(catalog_synced_at=catalog.checked_at))
    if guard.rowcount != 1:
        await session.rollback()
        raise ValueError(PREFERENCES_UNAVAILABLE)
    targets = (await session.scalars(select(ConnectionMonitorTarget).where(
        ConnectionMonitorTarget.reseller_id.is_(None), ConnectionMonitorTarget.test_enabled.is_(True),
    ).order_by(ConnectionMonitorTarget.id).limit(MAX_MONITOR_ENDPOINTS + 1))).all()
    if tuple(target.pg_host_id for target in targets) != selected:
        await session.rollback()
        raise ValueError(PREFERENCES_UNAVAILABLE)
    target = await session.scalar(select(ConnectionMonitorTarget).where(
        ConnectionMonitorTarget.reseller_id.is_(None), ConnectionMonitorTarget.pg_host_id == preferences.host_id,
    ).limit(1))
    is_new = target is None
    if target is None:
        target = ConnectionMonitorTarget(pg_host_id=preferences.host_id, generation="", endpoint_count=0)
        session.add(target)
    target.test_enabled = True
    target.public_name, target.is_public = preferences.public_name, preferences.is_public
    target.display_order = preferences.display_order
    changed = apply_target_plan(target, plan, now=datetime.now(timezone.utc))
    await session.flush()
    if changed or is_new:
        await session.execute(delete(ConnectionMonitorSnapshot).where(
            ConnectionMonitorSnapshot.reseller_id.is_(None), ConnectionMonitorSnapshot.target_id == target.id,
        ))
        session.add_all(initial_snapshots(target, plan))
    await session.commit()
    return target.id


async def pause_monitor_target(session: AsyncSession, access: MonitorAccess, *, target_id: int) -> None:
    if type(target_id) is not int or not 1 <= target_id <= 2147483647:
        raise ValueError(PREFERENCES_UNAVAILABLE)
    await require_monitor_owner(session, access)
    result = await session.execute(update(ConnectionMonitorTarget).where(
        ConnectionMonitorTarget.id == target_id, ConnectionMonitorTarget.reseller_id.is_(None), active_monitor_owner(access),
    ).values(test_enabled=False, is_public=False, generation="", endpoint_count=0, claim_token=None, claim_until=None, manual_pending=False))
    if result.rowcount != 1:
        await session.rollback()
        raise ValueError(PREFERENCES_UNAVAILABLE)
    await session.commit()
