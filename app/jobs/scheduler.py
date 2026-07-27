from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.models import UserService
from app.db.session import SessionLocal
from app.services.formatting import format_bytes, parse_expire
from app.services.pasarguard import get_pg

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def check_expiring_services(bot: Bot) -> None:
    async with SessionLocal() as session:
        result = await session.execute(select(UserService))
        services = list(result.scalars().all())
        pg = get_pg()
        for svc in services:
            if not svc.subscription_token:
                continue
            try:
                info = await pg.subscription_info(svc.subscription_token)
            except Exception:
                continue
            expire = parse_expire(info.get("expire"))
            used = float(info.get("used_traffic") or 0)
            limit = info.get("data_limit")
            owner = svc.owner
            # refresh relationship
            await session.refresh(svc, attribute_names=["owner"])
            from app.db.models import BotUser

            user = await session.get(BotUser, svc.bot_user_id)
            if not user:
                continue

            if expire and not svc.notified_expire:
                remaining = expire - datetime.now(timezone.utc)
                if remaining.total_seconds() <= 3 * 86400:
                    try:
                        await bot.send_message(
                            user.telegram_id,
                            f"⏰ سرویس <b>{svc.pg_username}</b> تا ۳ روز دیگر منقضی می‌شود. از بخش سرویس‌ها تمدید کنید.",
                        )
                        svc.notified_expire = True
                    except Exception:
                        pass

            if limit and not svc.notified_traffic:
                try:
                    ratio = used / float(limit)
                except Exception:
                    ratio = 0
                if ratio >= 0.9:
                    try:
                        await bot.send_message(
                            user.telegram_id,
                            f"📉 حجم سرویس <b>{svc.pg_username}</b> به {format_bytes(used)} از {format_bytes(limit)} رسیده است.",
                        )
                        svc.notified_traffic = True
                    except Exception:
                        pass
        await session.commit()


def start_scheduler(bot: Bot) -> None:
    if scheduler.running:
        return
    scheduler.add_job(check_expiring_services, "interval", hours=6, args=[bot], id="expiry")
    scheduler.start()
    logger.info("Scheduler started")
