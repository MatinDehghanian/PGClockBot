"""Telegram Mini App (WebApp) initData validation and persona resolution."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import BotUser, ResellerProfile, Role
from app.services.platform_identity import is_bot_platform_admin


def validate_webapp_init_data(init_data: str, *, bot_token: str | None = None) -> dict[str, Any]:
    """Validate Telegram WebApp ``initData`` HMAC and freshness; return user dict."""
    settings = get_settings()
    token = (bot_token or settings.bot_token or "").strip()
    if not token:
        raise HTTPException(503, "bot token missing")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "missing hash")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        raise HTTPException(401, "bad initData")
    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except (TypeError, ValueError):
        raise HTTPException(401, "bad auth_date")
    now = time.time()
    # Reject future skew (>5m) and stale initData (>10m)
    if auth_date <= 0 or auth_date > now + 300 or now - auth_date > 600:
        raise HTTPException(401, "expired")
    try:
        user = json.loads(parsed.get("user", "{}") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(401, "bad user")
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(401, "bad user")
    return user


def init_data_from_request(request: Request) -> str:
    """Header only — never accept initData in query strings (logs/history leakage)."""
    init_data = request.headers.get("X-Telegram-Init-Data") or ""
    if not init_data.strip():
        raise HTTPException(401, "no initData")
    return init_data


async def load_mini_user(session: AsyncSession, request: Request) -> BotUser:
    """Validate initData and load the BotUser row (must have /start'd).

    Blocked accounts are rejected (parity with bot middleware).
    """
    tg_user = validate_webapp_init_data(init_data_from_request(request))
    tg_id = tg_user.get("id")
    result = await session.execute(select(BotUser).where(BotUser.telegram_id == tg_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "start the bot first")
    if bool(getattr(user, "is_blocked", False)):
        raise HTTPException(403, "دسترسی شما مسدود شده است")
    return user


def resolve_mini_persona(user: BotUser) -> str:
    """Map BotUser → miniapp shell: admin | reseller | user."""
    if is_bot_platform_admin(user):
        return "admin"
    if (user.role or "").strip() == Role.RESELLER.value:
        return "reseller"
    return "user"


async def assert_mini_force_join(session: AsyncSession, user: BotUser) -> None:
    """Mirror bot ForceJoinMiddleware for Mini App commerce (users only).

    Admin/reseller personas are not gated (same as Telegram middleware).
    """
    if resolve_mini_persona(user) != "user":
        return
    from aiogram import Bot

    from app.bot.middlewares import check_force_join_all
    from app.services.users import (
        get_all_settings,
        on,
        parse_force_join_channels,
        parse_force_join_entries,
    )

    ui = await get_all_settings(session)
    if not on(ui.get("force_join_enabled")):
        return
    raw_channels = ui.get("force_join_channel")
    channels = parse_force_join_channels(raw_channels)
    if not channels:
        return
    entries = parse_force_join_entries(raw_channels)
    token = (get_settings().bot_token or "").strip()
    if not token:
        raise HTTPException(503, "bot token missing")
    bot = Bot(token=token)
    try:
        missing, unverified = await check_force_join_all(
            bot,
            int(user.telegram_id),
            channels,
            entries=entries,
        )
    finally:
        await bot.session.close()
    if missing or unverified:
        raise HTTPException(
            403,
            "ابتدا در کانال‌های اجباری عضو شوید و از ربات عضویت را تأیید کنید",
        )


async def load_reseller_profile(
    session: AsyncSession, user: BotUser
) -> ResellerProfile | None:
    if (user.role or "").strip() != Role.RESELLER.value:
        return None
    result = await session.execute(
        select(ResellerProfile).where(ResellerProfile.user_id == user.id)
    )
    return result.scalar_one_or_none()
