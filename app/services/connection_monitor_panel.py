"""Fresh authenticated catalog and dedicated-account evidence from the single panel."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.connection_monitor_settings import ACCOUNT_UNAVAILABLE, _validate_account, reveal_monitor_token
from app.services.pasarguard import get_pg


@dataclass(frozen=True, slots=True)
class MonitorAccount:
    pg_user_id: int
    revision: str
    encrypted_token: str = field(repr=False)
    username: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class MonitorCatalog:
    hosts: list[dict[str, Any]] = field(repr=False)
    inbounds: list[dict[str, Any]] = field(repr=False)
    native_configs: list[dict[str, Any]] = field(repr=False)
    checked_at: datetime


async def read_monitor_catalog(account: MonitorAccount) -> MonitorCatalog:
    pg = get_pg()
    token = await reveal_monitor_token(account.encrypted_token)
    async with asyncio.timeout(10):
        admin, user, hosts, inbounds = await asyncio.gather(
            pg.get_current_admin(), pg.get_user_by_id(account.pg_user_id), pg.get_hosts(), pg.get_inbounds_details(),
        )
        if not isinstance(admin, dict) or admin.get("is_owner") is not True or not isinstance(user, dict):
            raise ValueError(ACCOUNT_UNAVAILABLE)
        if not isinstance(user.get("username"), str) or not user["username"]:
            raise ValueError(ACCOUNT_UNAVAILABLE)
        user_id, current_token = _validate_account(user, username=account.username, expected_admin=str(admin.get("username") or "").lower())
        revision = hashlib.sha256(f"{user_id}:{current_token}".encode()).hexdigest()
        if user_id != account.pg_user_id or not secrets.compare_digest(token, current_token) or not secrets.compare_digest(revision, account.revision):
            raise ValueError(ACCOUNT_UNAVAILABLE)
        native = await pg.subscription_xray(token)
    return MonitorCatalog(hosts, inbounds, native, datetime.now(timezone.utc))
