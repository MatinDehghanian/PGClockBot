from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from aiogram.types import Update
from fastapi import Request
from sqlalchemy import select

from app.api.app import create_api_app
from app.bot import create_bot, create_dispatcher
from app.config import get_settings
from app.db.models import Plan
from app.db.session import SessionLocal, init_db
from app.jobs.scheduler import start_scheduler
from app.services.pasarguard import get_pg
from app.services.users import ensure_default_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("pgclock")


async def seed_demo_plan() -> None:
    async with SessionLocal() as session:
        await ensure_default_settings(session)
        result = await session.execute(select(Plan).limit(1))
        if result.scalar_one_or_none() is None:
            session.add(
                Plan(
                    name="ماهانه ۳۰ گیگ",
                    description="پلن شروع — تمپلیت را از وب‌پنل تنظیم کنید",
                    price=150000,
                    duration_days=30,
                    data_limit_gb=30,
                    pg_template_id=None,
                    is_active=True,
                    sort_order=1,
                )
            )
            session.add(
                Plan(
                    name="ماهانه نامحدود",
                    description="حجم نامحدود یک‌ماهه",
                    price=250000,
                    duration_days=30,
                    data_limit_gb=None,
                    is_active=True,
                    sort_order=2,
                )
            )
            await session.commit()
            logger.info("Seeded demo plans")


def main() -> None:
    settings = get_settings()
    bot = create_bot()
    dp = create_dispatcher()

    @asynccontextmanager
    async def lifespan(app):
        await init_db()
        await seed_demo_plan()
        start_scheduler(bot)
        poll_task = None
        if settings.webhook_url.strip():
            url = settings.webhook_url.rstrip("/") + settings.webhook_path
            await bot.set_webhook(url, drop_pending_updates=True)
            logger.info("Webhook set: %s", url)
        else:
            await bot.delete_webhook(drop_pending_updates=True)

            async def _poll():
                logger.info("Starting polling…")
                await dp.start_polling(bot)

            poll_task = asyncio.create_task(_poll())
        try:
            yield
        finally:
            if poll_task:
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass
            if settings.webhook_url.strip():
                await bot.delete_webhook(drop_pending_updates=False)
            await get_pg().close()
            await bot.session.close()

    api = create_api_app(lifespan=lifespan)

    if settings.webhook_url.strip():

        @api.post(settings.webhook_path)
        async def telegram_webhook(request: Request):
            data = await request.json()
            update = Update.model_validate(data, context={"bot": bot})
            await dp.feed_update(bot, update)
            return {"ok": True}

    uvicorn.run(api, host=settings.web_host, port=settings.web_port, log_level="info")


if __name__ == "__main__":
    main()
