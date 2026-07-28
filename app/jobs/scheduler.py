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


def _as_int(val, default: int) -> int:
    try:
        return int(float(val))
    except Exception:
        return default


async def check_expiring_services(bot: Bot) -> None:
    async with SessionLocal() as session:
        from app.services.users import get_all_settings, on

        ui = await get_all_settings(session)
        enabled = on(ui.get("user_alert_low_enabled", "0"))
        if not enabled:
            return

        traffic_pct = max(1, min(99, _as_int(ui.get("user_alert_low_traffic_pct"), 20)))
        time_pct = max(1, min(99, _as_int(ui.get("user_alert_low_time_pct"), 20)))

        result = await session.execute(select(UserService))
        services = list(result.scalars().all())
        pg = get_pg()
        now = datetime.now(timezone.utc)

        for svc in services:
            if not svc.subscription_token:
                continue
            try:
                info = await pg.subscription_info(svc.subscription_token)
            except Exception:
                continue

            from app.db.models import BotUser

            user = await session.get(BotUser, svc.bot_user_id)
            if not user or user.is_blocked:
                continue

            # --- remaining TIME percent ---
            if not svc.notified_expire:
                expire = parse_expire(info.get("expire"))
                created = svc.created_at
                if created and created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if expire and created and expire > created:
                    total = (expire - created).total_seconds()
                    remaining = (expire - now).total_seconds()
                    if total > 0 and remaining >= 0:
                        rem_pct = (remaining / total) * 100
                        if rem_pct <= time_pct:
                            try:
                                await bot.send_message(
                                    user.telegram_id,
                                    f"⏰ زمان سرویس <b>{svc.pg_username}</b> به کمتر از "
                                    f"<b>{time_pct}٪</b> رسیده است.\n"
                                    "از بخش سرویس‌ها تمدید کنید.",
                                )
                                svc.notified_expire = True
                            except Exception:
                                pass

            # --- remaining TRAFFIC percent ---
            if not svc.notified_traffic:
                used = float(info.get("used_traffic") or 0)
                limit = info.get("data_limit")
                if limit:
                    try:
                        limit_f = float(limit)
                    except Exception:
                        limit_f = 0
                    if limit_f > 0:
                        rem_pct = max(0.0, (1.0 - (used / limit_f)) * 100)
                        if rem_pct <= traffic_pct:
                            try:
                                await bot.send_message(
                                    user.telegram_id,
                                    f"📉 حجم باقی‌مانده سرویس <b>{svc.pg_username}</b> کمتر از "
                                    f"<b>{traffic_pct}٪</b> است "
                                    f"({format_bytes(used)} از {format_bytes(limit_f)}).",
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
