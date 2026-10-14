"""Add a service created outside the bot to a customer's «سرویس‌های من».

A subscription link is a bearer secret that people share, so possession of it is not
enough. Before a service is attached the panel user behind the link must

* belong to the panel admin of the shop the customer buys from (never another shop,
  never another admin), checked against the authenticated panel record;
* not be attached to any other customer, which is also enforced by a partial unique
  index so two simultaneous claims cannot both win.

Failures answer with one generic message so the existence or owner of someone else's
service is never revealed, failed tries are limited per customer, and every try is
logged with a hash of the token only. Nothing is written to the panel.

An imported service is renewable and can buy add-on packs like any other service, but it
was not sold by the bot: it can never be cancelled for a refund, and removing it from the
list only detaches it, never deleting the panel user.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import BotUser, ResellerProfile, ServiceImportAttempt, UserService
from app.services.pasarguard import (
    PasarGuardError,
    absolutize_subscription_url,
    extract_sub_token,
    get_pg,
    get_pg_for_reseller,
    user_subscription_url,
)
from app.services.pg_user_scope import pg_user_owner_username

logger = logging.getLogger(__name__)

REMARK_IMPORTED = "imported"
REMARK_LINKED = "linked"
SETTING_KEY = "service_import_enabled"

MAX_LINK_LENGTH = 2048
MAX_FAILED_ATTEMPTS = 5
ATTEMPT_WINDOW = timedelta(hours=1)
ATTEMPT_RETENTION = timedelta(days=7)
MAX_IMPORTED_PER_USER = 5
_BARE_TOKEN = re.compile(r"^[A-Za-z0-9._~-]{8,1024}$")

GENERIC_REFUSAL = "این لینک قابل افزودن نیست. لینک اشتراک را بررسی کنید یا با پشتیبانی تماس بگیرید."
RATE_LIMITED = "تعداد تلاش‌های ناموفق زیاد بود. کمی بعد دوباره تلاش کنید."
PANEL_UNAVAILABLE = "اتصال به پنل برقرار نشد. کمی بعد دوباره تلاش کنید."
LIMIT_REACHED = "به سقف تعداد سرویس‌های قابل افزودن رسیده‌اید."
NOT_ENABLED = "افزودن سرویس قبلی در این فروشگاه فعال نیست."


class ImportOutcome(StrEnum):
    ADDED = "added"
    UPGRADED = "upgraded"
    ALREADY_YOURS = "already_yours"


@dataclass(frozen=True, slots=True)
class ImportResult:
    outcome: ImportOutcome
    service: UserService
    info: dict[str, Any]


class ServiceImportError(ValueError):
    """Refusal with a customer-safe Persian message."""


def is_external_service(service: UserService | None) -> bool:
    """Attached from outside the bot (view-only link or imported): no cancellation, never delete the panel user."""
    return bool(service) and (service.remark or "").strip() in {REMARK_LINKED, REMARK_IMPORTED}


def parse_subscription_token(raw: str | None) -> str | None:
    """Token from a subscription link or a bare token; ``None`` for anything else."""
    text = (raw or "").strip()
    if not text or len(text) > MAX_LINK_LENGTH:
        return None
    if "/" in text or "://" in text:
        return extract_sub_token(text)
    return text if _BARE_TOKEN.match(text) else None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _record_attempt(session: AsyncSession, user_id: int, token: str, outcome: str) -> None:
    """Persist one try (separate commit, so a refused claim still counts) and prune old rows."""
    now = datetime.now(timezone.utc)
    session.add(ServiceImportAttempt(bot_user_id=int(user_id), token_hash=_token_hash(token), outcome=outcome))
    await session.execute(
        delete(ServiceImportAttempt).where(
            ServiceImportAttempt.bot_user_id == int(user_id),
            ServiceImportAttempt.created_at < now - ATTEMPT_RETENTION,
        )
    )
    await session.commit()


async def _failed_attempts(session: AsyncSession, user_id: int) -> int:
    since = datetime.now(timezone.utc) - ATTEMPT_WINDOW
    ok = {ImportOutcome.ADDED.value, ImportOutcome.UPGRADED.value, ImportOutcome.ALREADY_YOURS.value, "error"}
    return int(
        await session.scalar(
            select(func.count()).select_from(ServiceImportAttempt).where(
                ServiceImportAttempt.bot_user_id == int(user_id),
                ServiceImportAttempt.created_at >= since,
                ServiceImportAttempt.outcome.not_in(ok),
            )
        )
        or 0
    )


async def _panel_client_and_admin(session: AsyncSession, shop_id: int | None) -> tuple[Any, str]:
    """Panel client of the shop and the panel admin whose users the shop may attach."""
    if shop_id is None:
        return get_pg(), (get_settings().pg_username or "").strip().lower()
    profile = await session.scalar(select(ResellerProfile).where(ResellerProfile.user_id == int(shop_id)))
    admin = ((profile.pg_admin_username if profile else "") or "").strip().lower()
    return await get_pg_for_reseller(session, int(shop_id)), admin


async def _panel_user(pg: Any, token: str) -> dict[str, Any]:
    """Authenticated panel record of the user behind ``token`` (raises on any mismatch)."""
    info = await pg.subscription_info(token)
    username = str((info or {}).get("username") or "").strip()
    if not username:
        raise ServiceImportError(GENERIC_REFUSAL)
    record = await pg.get_user_by_username(username)
    if not isinstance(record, dict) or str(record.get("username") or "").strip().lower() != username.lower():
        raise ServiceImportError(GENERIC_REFUSAL)
    return record


def _panel_user_id(record: dict[str, Any]) -> int:
    value = record.get("id")
    if type(value) is not int or value <= 0:
        raise ServiceImportError(GENERIC_REFUSAL)
    return value


async def _existing_rows(session: AsyncSession, pg_user_id: int, token: str) -> list[UserService]:
    rows = await session.scalars(
        select(UserService).where(
            (UserService.pg_user_id == pg_user_id) | (UserService.subscription_token == token)
        ).limit(20)
    )
    return list(rows.all())


async def import_existing_service(
    session: AsyncSession, *, user: BotUser, raw_link: str, shop_id: int | None, renewable: bool = True
) -> ImportResult:
    """Attach the panel service behind ``raw_link`` to ``user`` or raise ``ServiceImportError``.

    ``renewable=False`` keeps the older view-only attachment (used by the deep link while
    importing is switched off); both go through the same checks.
    """
    user_id = int(user.id)  # a rollback below expires ``user``; keep the id
    token = parse_subscription_token(raw_link)
    if token is None:
        await _record_attempt(session, user_id, raw_link[:64] or "-", "invalid")
        raise ServiceImportError(GENERIC_REFUSAL)
    if await _failed_attempts(session, user_id) >= MAX_FAILED_ATTEMPTS:
        raise ServiceImportError(RATE_LIMITED)
    try:
        result = await _attach(session, user, token, shop_id, renewable)
    except ServiceImportError:
        await session.rollback()
        await _record_attempt(session, user_id, token, "refused")
        raise
    except (PasarGuardError, httpx.HTTPError, TimeoutError) as exc:
        await session.rollback()
        if _is_not_found(exc):
            # An unknown or out-of-scope link is a failed guess and counts against the budget.
            await _record_attempt(session, user_id, token, "refused")
            raise ServiceImportError(GENERIC_REFUSAL) from None
        logger.warning("service import: panel call failed (%s)", type(exc).__name__, exc_info=True)
        await _record_attempt(session, user_id, token, "error")
        raise ServiceImportError(PANEL_UNAVAILABLE) from None
    await _record_attempt(session, user_id, token, result.outcome.value)
    return result


def _is_not_found(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) in {401, 403, 404}


async def _attach(session: AsyncSession, user: BotUser, token: str, shop_id: int | None, renewable: bool) -> ImportResult:
    if (user.reseller_id or None) != (shop_id or None) or user.is_blocked:
        raise ServiceImportError(GENERIC_REFUSAL)
    pg, expected_admin = await _panel_client_and_admin(session, shop_id)
    record = await _panel_user(pg, token)
    if not expected_admin or pg_user_owner_username(record) != expected_admin:
        raise ServiceImportError(GENERIC_REFUSAL)
    panel_id = _panel_user_id(record)

    mine: UserService | None = None
    for row in await _existing_rows(session, panel_id, token):
        if row.bot_user_id != user.id:
            raise ServiceImportError(GENERIC_REFUSAL)
        mine = mine or row
    wanted = REMARK_IMPORTED if renewable else REMARK_LINKED
    if mine is not None:
        if (mine.remark or "").strip() == REMARK_LINKED and renewable:
            mine.remark = REMARK_IMPORTED
            return await _commit(session, mine, record, ImportOutcome.UPGRADED)
        return ImportResult(ImportOutcome.ALREADY_YOURS, mine, record)

    if renewable and await _imported_count(session, user.id) >= MAX_IMPORTED_PER_USER:
        raise ServiceImportError(LIMIT_REACHED)
    sub_url = user_subscription_url(record) or absolutize_subscription_url(f"{get_settings().pg_subscription_path}/{token}")
    service = UserService(
        bot_user_id=user.id,
        pg_user_id=panel_id,
        pg_username=str(record.get("username") or "")[:128],
        subscription_url=sub_url,
        subscription_token=token,
        remark=wanted,
    )
    session.add(service)
    return await _commit(session, service, record, ImportOutcome.ADDED)


async def _commit(session: AsyncSession, service: UserService, record: dict[str, Any], outcome: ImportOutcome) -> ImportResult:
    try:
        await session.commit()
    except IntegrityError:
        # A concurrent claim of the same panel user won the unique index.
        raise ServiceImportError(GENERIC_REFUSAL) from None
    await session.refresh(service)
    return ImportResult(outcome, service, record)


async def _imported_count(session: AsyncSession, user_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(UserService).where(
                UserService.bot_user_id == int(user_id), UserService.remark == REMARK_IMPORTED
            )
        )
        or 0
    )
