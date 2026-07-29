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
from app.services.web_auth import load_web_admin

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
    # Always reload settings from project .env
    get_settings.cache_clear()
    settings = get_settings()
    has_token = bool((settings.bot_token or "").strip())
    bot = None
    dp = None
    if has_token:
        try:
            bot = create_bot()
            dp = create_dispatcher()
        except Exception:
            logger.exception("Bot init failed — starting web panel only")
            bot = None
            dp = None

    @asynccontextmanager
    async def lifespan(app):
        await init_db()
        try:
            await seed_demo_plan()
        except Exception:
            logger.exception("Demo plan seed failed — continuing")

        poll_task = None
        reseller_mgr = None
        panel_only = bot is None or dp is None

        if panel_only:
            logger.warning(
                "Web panel only mode (no bot yet). Open http://%s:%s/ to finish setup.",
                settings.web_host,
                settings.web_port,
            )
        else:
            try:
                start_scheduler(bot)
            except Exception:
                logger.exception("Scheduler failed to start")

            try:
                me = await bot.get_me()
                logger.info(
                    "Bot online as @%s (id=%s) · admins=%s",
                    me.username,
                    me.id,
                    settings.admin_ids,
                )
            except Exception:
                logger.exception(
                    "Cannot connect to Telegram — web panel stays up. "
                    "Fix BOT_TOKEN in /setup or .env and restart."
                )
                # Do not raise — panel must remain reachable
                panel_only = True

            if not panel_only:
                async def _pg_warmup() -> None:
                    try:
                        await get_pg().ensure_token()
                        logger.info("PasarGuard panel login OK · %s", get_settings().pg_base_url)
                    except Exception:
                        logger.exception(
                            "PasarGuard login FAILED — fix PG_BASE_URL / PG_USERNAME / PG_PASSWORD "
                            "(use https://host only, no path)"
                        )

                asyncio.create_task(_pg_warmup())

                if settings.webhook_url.strip():
                    url = settings.webhook_url.rstrip("/") + settings.webhook_path
                    secret = (settings.webhook_secret_token or "").strip()
                    if not secret:
                        from app.services.webhook_secret import ensure_webhook_secret

                        secret = ensure_webhook_secret()
                    try:
                        await bot.set_webhook(
                            url,
                            drop_pending_updates=True,
                            secret_token=secret,
                        )
                        logger.info("Webhook set: %s (secret token enabled)", url)
                    except Exception:
                        logger.exception("set_webhook failed")
                else:
                    try:
                        await bot.delete_webhook(drop_pending_updates=True)
                    except Exception:
                        logger.exception("delete_webhook failed")

                    async def _poll():
                        logger.info("Starting long-polling…")
                        try:
                            await dp.start_polling(bot)
                        except Exception:
                            logger.exception("Polling crashed")
                            raise

                    poll_task = asyncio.create_task(_poll())

                    def _on_done(task: asyncio.Task) -> None:
                        if task.cancelled():
                            return
                        exc = task.exception()
                        if exc:
                            logger.error("Polling task failed: %s", exc)

                    poll_task.add_done_callback(_on_done)

                # Reseller-owned bots always use getUpdates (independent of main webhook)
                try:
                    from app.services.reseller_bots import init_reseller_bot_manager

                    reseller_mgr = init_reseller_bot_manager(dp)
                    await reseller_mgr.start_all()
                except Exception:
                    logger.exception("Reseller bots failed to start")

        try:
            yield
        finally:
            if reseller_mgr is not None:
                try:
                    await reseller_mgr.stop_all()
                except Exception:
                    logger.exception("Reseller bots shutdown failed")
            if poll_task:
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass
            if bot is not None and settings.webhook_url.strip():
                try:
                    await bot.delete_webhook(drop_pending_updates=False)
                except Exception:
                    pass
            try:
                await get_pg().close()
            except Exception:
                pass
            if bot is not None:
                try:
                    await bot.session.close()
                except Exception:
                    pass

    api = create_api_app(lifespan=lifespan)

    if bot is not None and dp is not None and settings.webhook_url.strip():
        from fastapi.responses import JSONResponse

        from app.services.webhook_secret import ensure_webhook_secret

        webhook_secret = (settings.webhook_secret_token or "").strip() or ensure_webhook_secret()

        @api.post(settings.webhook_path)
        async def telegram_webhook(request: Request):
            header = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
            if not header or header != webhook_secret:
                return JSONResponse({"ok": False}, status_code=403)
            data = await request.json()
            update = Update.model_validate(data, context={"bot": bot})
            await dp.feed_update(bot, update)
            return {"ok": True}

    from app.services.setup_wizard import ensure_setup_gate_token, is_setup_complete
    from app.services.web_auth import repair_web_admin_from_env

    if is_setup_complete():
        try:
            creds = repair_web_admin_from_env()
        except Exception:
            creds = load_web_admin()
    else:
        creds = load_web_admin()

    from app.services.ssl_certs import uvicorn_ssl_kwargs

    ssl_kwargs = uvicorn_ssl_kwargs() or {}
    scheme = "https" if ssl_kwargs else "http"
    host_hint = settings.web_host if settings.web_host not in {"0.0.0.0", "::"} else "127.0.0.1"
    entry = f"{scheme}://{host_hint}:{settings.web_port}/"
    if not creds.get("password") or not is_setup_complete():
        gate = ensure_setup_gate_token()
        logger.warning(
            "First-run wizard pending — open gated URL: %s?gate=%s",
            entry.rstrip("/"),
            gate,
        )
    else:
        logger.info(
            "Web panel ready · user=%s · %s",
            creds.get("username") or "admin",
            entry,
        )
        if ssl_kwargs:
            logger.info("TLS enabled · cert=%s", ssl_kwargs.get("ssl_certfile"))

    uvicorn.run(
        api,
        host=settings.web_host,
        port=settings.web_port,
        log_level="info",
        **ssl_kwargs,
    )


if __name__ == "__main__":
    main()
