"""Private monitor settings and encrypted references to an existing panel account."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import Integer, exists, func, insert, literal, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import ConnectionMonitorState, ConnectionMonitorTarget, UserService
from app.services.connection_monitor_access import (
    MONITOR_ACCESS_DENIED,
    MonitorAccess,
    active_monitor_owner,
    require_monitor_owner,
)
from app.services.db_safe import rollback_quiet
from app.services.credential_policy import validate_pg_username
from app.services.formatting import parse_expire
from app.services.pasarguard import PasarGuardError, get_pg
from app.services.pg_user_scope import pg_user_owner_username
from app.services.secret_box import decrypt_secret, encrypt_secret
from app.services.service_import import parse_subscription_token


logger = logging.getLogger(__name__)
LOCAL_PROBE_ID = "local"
ACCOUNT_UNAVAILABLE = "حساب اختصاصی پایش معتبر و در دسترس نیست."


@dataclass(frozen=True, slots=True)
class MonitorSettings:
    id: int
    enabled: bool
    pg_user_id: int | None
    has_account: bool


async def monitor_settings(session: AsyncSession, access: MonitorAccess) -> MonitorSettings:
    await require_monitor_owner(session, access)
    query = select(ConnectionMonitorState).where(
        ConnectionMonitorState.reseller_id.is_(None), ConnectionMonitorState.probe_id == LOCAL_PROBE_ID,
    ).limit(1)
    state = await session.scalar(query)
    if state is None:
        try:
            async with session.begin_nested():
                await session.execute(insert(ConnectionMonitorState).from_select(
                    ["reseller_id", "probe_id"],
                    select(literal(None, Integer), literal(LOCAL_PROBE_ID)).where(active_monitor_owner(access)),
                ))
        except IntegrityError:
            # Only the competing initial insert is rolled back by the savepoint.
            await rollback_quiet(session)
            logger.debug("Monitor state initialization raced with another request")
        state = await session.scalar(query)
    if state is None:
        raise ValueError(MONITOR_ACCESS_DENIED)
    result = MonitorSettings(state.id, state.enabled, state.pg_user_id, bool(state.subscription_token_enc and state.pg_username))
    await session.commit()
    return result


def _validate_account(record: object, *, username: str, expected_admin: str) -> tuple[int, str]:
    if not isinstance(record, dict) or record.get("username") != username:
        raise ValueError(ACCOUNT_UNAVAILABLE)
    user_id = record.get("id")
    if type(user_id) is not int or not 1 <= user_id <= 2147483647:
        raise ValueError(ACCOUNT_UNAVAILABLE)
    if not expected_admin or pg_user_owner_username(record) != expected_admin:
        raise ValueError(ACCOUNT_UNAVAILABLE)
    if record.get("status") != "active":
        raise ValueError(ACCOUNT_UNAVAILABLE)
    _validate_account_capacity(record)
    subscription_url = record.get("subscription_url")
    token = parse_subscription_token(subscription_url) if isinstance(subscription_url, str) else None
    if not token:
        raise ValueError(ACCOUNT_UNAVAILABLE)
    return user_id, token


def _validate_account_capacity(record: dict[str, Any]) -> None:
    used, limit = record.get("used_traffic"), record.get("data_limit")
    maximum = 9223372036854775807
    if type(used) is not int or not 0 <= used <= maximum:
        raise ValueError(ACCOUNT_UNAVAILABLE)
    if limit is not None and (type(limit) is not int or not 0 <= limit <= maximum):
        raise ValueError(ACCOUNT_UNAVAILABLE)
    if limit and used >= limit:
        raise ValueError(ACCOUNT_UNAVAILABLE)
    expire = record.get("expire")
    if expire is None or (type(expire) is int and expire == 0):
        return
    if type(expire) not in (int, str):
        raise ValueError(ACCOUNT_UNAVAILABLE)
    try:
        parsed = parse_expire(expire)
    except (ValueError, OverflowError, OSError):
        raise ValueError(ACCOUNT_UNAVAILABLE) from None
    if parsed is None or parsed.tzinfo is None or parsed <= datetime.now(timezone.utc):
        raise ValueError(ACCOUNT_UNAVAILABLE)


async def _read_account(username: str) -> tuple[int, str]:
    pg = get_pg()
    try:
        async with asyncio.timeout(5):
            admin = await pg.get_current_admin()
            if not isinstance(admin, dict) or admin.get("is_owner") is not True:
                raise ValueError(ACCOUNT_UNAVAILABLE)
            expected_admin = str(admin.get("username") or "").strip().lower()
            configured_admin = (get_settings().pg_username or "").strip().lower()
            if configured_admin and configured_admin != expected_admin:
                raise ValueError(ACCOUNT_UNAVAILABLE)
            record = await pg.get_user_by_username(username)
    except (PasarGuardError, httpx.HTTPError, TimeoutError):
        logger.warning("Monitoring account read failed")
        raise ValueError(ACCOUNT_UNAVAILABLE) from None
    return _validate_account(record, username=username, expected_admin=expected_admin)


async def set_monitor_account(session: AsyncSession, access: MonitorAccess, *, username: str) -> MonitorSettings:
    if not isinstance(username, str) or not 1 <= len(username) <= 128 or username != username.strip():
        raise ValueError(ACCOUNT_UNAVAILABLE)
    cleaned, error = validate_pg_username(username)
    if error or cleaned != username:
        raise ValueError(ACCOUNT_UNAVAILABLE)
    settings = await monitor_settings(session, access)
    user_id, token = await _read_account(username)
    encrypted = await asyncio.to_thread(encrypt_secret, token)
    if not encrypted:
        raise ValueError(ACCOUNT_UNAVAILABLE)
    # This is an exclusion check only: a monitoring account must not be sold or
    # attached to any customer, including a different shop. No customer row leaves DB.
    customer_account = exists(select(UserService.id).where(or_(
        UserService.pg_user_id == user_id, func.lower(UserService.pg_username) == username.lower(),
    )))
    result = await session.execute(update(ConnectionMonitorState).where(
        ConnectionMonitorState.id == settings.id, ConnectionMonitorState.reseller_id.is_(None),
        active_monitor_owner(access), ~customer_account,
    ).values(
        pg_user_id=user_id, pg_username=username, subscription_token_enc=encrypted,
        account_revision=hashlib.sha256(f"{user_id}:{token}".encode()).hexdigest(), enabled=False,
        cycle_token=None, cycle_lease_until=None, catalog_synced_at=None,
    ))
    if result.rowcount != 1:
        await rollback_quiet(session)
        raise ValueError(ACCOUNT_UNAVAILABLE)
    await session.execute(update(ConnectionMonitorTarget).where(
        ConnectionMonitorTarget.reseller_id.is_(None),
    ).values(generation="", endpoint_count=0, is_public=False, claim_token=None, claim_until=None))
    await session.commit()
    return MonitorSettings(settings.id, False, user_id, True)


async def reveal_monitor_token(encrypted: str | None) -> str:
    """An unreadable reference must stop the check rather than imply a host outage."""
    token = await asyncio.to_thread(decrypt_secret, encrypted)
    if not token:
        raise ValueError(ACCOUNT_UNAVAILABLE)
    return token
