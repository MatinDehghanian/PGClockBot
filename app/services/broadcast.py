from __future__ import annotations

"""Admin broadcast / bulk messaging to bot users."""

import asyncio
import logging

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, BroadcastLog, Role

logger = logging.getLogger("pgclock.broadcast")

AUDIENCE_LABELS = {
    "all": "همه",
    "users": "کاربران عادی",
    "resellers": "نمایندگان",
    "admins": "ادمین‌ها",
}


async def list_broadcast_targets(
    session: AsyncSession,
    *,
    audience: str = "all",
) -> list[BotUser]:
    q = select(BotUser).where(BotUser.is_blocked.is_(False))
    if audience == "users":
        q = q.where(BotUser.role == Role.USER.value)
    elif audience == "resellers":
        q = q.where(BotUser.role == Role.RESELLER.value)
    elif audience == "admins":
        q = q.where(BotUser.role == Role.ADMIN.value)
    result = await session.execute(q.order_by(BotUser.id))
    return list(result.scalars().all())


async def list_broadcast_history(session: AsyncSession, *, limit: int = 50) -> list[BroadcastLog]:
    result = await session.execute(
        select(BroadcastLog).order_by(BroadcastLog.id.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def send_broadcast(
    bot: Bot,
    session: AsyncSession,
    *,
    text: str,
    audience: str = "all",
    delay: float = 0.05,
    created_by: str | None = None,
) -> dict:
    """Send HTML text to matching users and persist history. Returns counts."""
    body = (text or "").strip()
    if not body:
        raise ValueError("متن پیام خالی است")
    if len(body) > 4000:
        raise ValueError("متن پیام خیلی طولانی است (حداکثر ۴۰۰۰)")

    users = await list_broadcast_targets(session, audience=audience)
    ok = 0
    fail = 0
    for u in users:
        try:
            await bot.send_message(u.telegram_id, body, parse_mode="HTML")
            ok += 1
        except Exception as e:
            fail += 1
            logger.debug("broadcast fail tg=%s: %s", u.telegram_id, e)
        if delay:
            await asyncio.sleep(delay)

    log = BroadcastLog(
        audience=audience,
        text=body,
        total=len(users),
        ok_count=ok,
        fail_count=fail,
        created_by=(created_by or "")[:128] or None,
    )
    session.add(log)
    await session.commit()

    return {
        "total": len(users),
        "ok": ok,
        "fail": fail,
        "audience": audience,
        "log_id": log.id,
    }
