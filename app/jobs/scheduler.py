from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.models import BotUser, ResellerProfile, UserService
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


def _resolve_send_bot(
    main_bot: Bot,
    reseller_user_id: int | None,
    profile_by_user: dict[int, int],
) -> Bot:
    """Prefer the shop's dedicated bot when alerting that shop's customers."""
    if not reseller_user_id:
        return main_bot
    from app.services.reseller_bots import get_reseller_bot_manager

    mgr = get_reseller_bot_manager()
    if not mgr:
        return main_bot
    pid = profile_by_user.get(int(reseller_user_id))
    if pid is None:
        return main_bot
    shop_bot = mgr.bot_for_profile_id(int(pid))
    return shop_bot or main_bot


async def check_expiring_services(bot: Bot) -> None:
    async with SessionLocal() as session:
        from app.services.users import get_all_settings, on

        result = await session.execute(select(UserService))
        services = list(result.scalars().all())
        if not services:
            return

        profiles = (
            await session.execute(
                select(ResellerProfile.user_id, ResellerProfile.id).where(
                    ResellerProfile.is_active.is_(True),
                    ResellerProfile.bot_token.is_not(None),
                )
            )
        ).all()
        profile_by_user = {int(uid): int(pid) for uid, pid in profiles if uid is not None}

        settings_cache: dict[int | None, dict] = {}

        async def ui_for(reseller_user_id: int | None) -> dict:
            key = int(reseller_user_id) if reseller_user_id else None
            if key not in settings_cache:
                settings_cache[key] = await get_all_settings(session, reseller_id=key)
            return settings_cache[key]

        pg = get_pg()
        now = datetime.now(timezone.utc)

        for svc in services:
            if not svc.subscription_token:
                continue
            try:
                info = await pg.subscription_info(svc.subscription_token)
            except Exception:
                continue

            user = await session.get(BotUser, svc.bot_user_id)
            if not user or user.is_blocked:
                continue

            ui = await ui_for(user.reseller_id)
            if not on(ui.get("user_alert_low_enabled", "0")):
                continue

            traffic_pct = max(1, min(99, _as_int(ui.get("user_alert_low_traffic_pct"), 20)))
            time_pct = max(1, min(99, _as_int(ui.get("user_alert_low_time_pct"), 20)))
            send_bot = _resolve_send_bot(bot, user.reseller_id, profile_by_user)

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
                                await send_bot.send_message(
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
                                await send_bot.send_message(
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
