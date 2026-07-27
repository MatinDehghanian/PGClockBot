from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.services.users import get_or_create_user


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with SessionLocal() as session:
            data["session"] = session
            return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        session: AsyncSession = data["session"]
        tg_user = None
        if isinstance(event, Message) and event.from_user:
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            tg_user = event.from_user
        if tg_user:
            user = await get_or_create_user(
                session,
                tg_user.id,
                username=tg_user.username,
                full_name=tg_user.full_name,
            )
            data["db_user"] = user
            if user.is_blocked:
                if isinstance(event, Message):
                    await event.answer("دسترسی شما مسدود شده است.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("دسترسی شما مسدود شده است.", show_alert=True)
                return None
        return await handler(event, data)
