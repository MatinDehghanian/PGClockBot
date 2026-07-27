from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.middlewares import DbSessionMiddleware, ErrorLogMiddleware, UserMiddleware
from app.config import get_settings


def create_bot() -> Bot:
    settings = get_settings()
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(ErrorLogMiddleware())
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(UserMiddleware())

    from app.bot.handlers import admin, payments, reseller, shop, start, support, services, wallet

    dp.include_router(start.router)
    dp.include_router(shop.router)
    dp.include_router(wallet.router)
    dp.include_router(services.router)
    dp.include_router(support.router)
    dp.include_router(payments.router)
    dp.include_router(reseller.router)
    dp.include_router(admin.router)
    return dp
