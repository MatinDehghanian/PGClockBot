from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject

from app.bot.middlewares import DbSessionMiddleware, ErrorLogMiddleware, UserMiddleware
from app.config import get_settings


class _BlockPlatformAdminOnResellerBot(BaseMiddleware):
    """Prevent main-panel admin tools from running on reseller-owned bots."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if data.get("is_reseller_bot"):
            return None
        return await handler(event, data)


def create_bot(token: str | None = None) -> Bot:
    settings = get_settings()
    return Bot(
        token=(token or settings.bot_token).strip(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(ErrorLogMiddleware())
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(UserMiddleware())

    from app.bot.handlers import (
        admin,
        admin_backup,
        admin_settings,
        payments,
        reseller,
        reseller_settings,
        shop,
        start,
        support,
        services,
        wallet,
    )

    dp.include_router(start.router)
    dp.include_router(shop.router)
    dp.include_router(wallet.router)
    dp.include_router(services.router)
    dp.include_router(support.router)
    dp.include_router(payments.router)
    dp.include_router(reseller.router)
    dp.include_router(reseller_settings.router)
    dp.include_router(admin_settings.router)
    dp.include_router(admin_backup.router)
    dp.include_router(admin.router)

    block = _BlockPlatformAdminOnResellerBot()
    for r in (admin.router, admin_backup.router, admin_settings.router):
        r.message.middleware(block)
        r.callback_query.middleware(block)
    return dp
