from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.services.users import get_or_create_user

logger = logging.getLogger("pgclock.bot")


def _extract_from_user(event: TelegramObject):
    if isinstance(event, Message) and event.from_user:
        return event.from_user
    if isinstance(event, CallbackQuery) and event.from_user:
        return event.from_user
    if isinstance(event, Update):
        if event.message and event.message.from_user:
            return event.message.from_user
        if event.callback_query and event.callback_query.from_user:
            return event.callback_query.from_user
        if event.edited_message and event.edited_message.from_user:
            return event.edited_message.from_user
    return None


def _reply_message(event: TelegramObject) -> Message | None:
    if isinstance(event, Message):
        return event
    if isinstance(event, CallbackQuery) and event.message and isinstance(event.message, Message):
        return event.message
    if isinstance(event, Update):
        if event.message:
            return event.message
        if event.edited_message:
            return event.edited_message
        cq = event.callback_query
        if cq and cq.message and isinstance(cq.message, Message):
            return cq.message
    return None


def _is_benign_telegram_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        "message is not modified" in text
        or "query is too old" in text
        or "query id is invalid" in text
        or "message to delete not found" in text
        or "message can't be deleted" in text
    )


def _extract_start_payload(event: TelegramObject) -> str | None:
    text = None
    if isinstance(event, Message) and event.text:
        text = event.text
    elif isinstance(event, Update) and event.message and event.message.text:
        text = event.message.text
    if not text:
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) == 2 and parts[0].startswith("/start"):
        return parts[1].strip()
    return None


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
        tg_user = _extract_from_user(event)
        if tg_user:
            referred_by_code = None
            payload = _extract_start_payload(event)
            if payload and payload.startswith("ref_"):
                referred_by_code = payload[4:].strip()
            try:
                user = await get_or_create_user(
                    session,
                    tg_user.id,
                    username=tg_user.username,
                    full_name=tg_user.full_name,
                    referred_by_code=referred_by_code,
                )
            except Exception:
                logger.exception("Failed to load/create bot user tg_id=%s", tg_user.id)
                msg = _reply_message(event)
                if msg:
                    try:
                        await msg.answer("خطای موقت. چند ثانیه بعد دوباره /start بزنید.")
                    except Exception:
                        pass
                return None
            data["db_user"] = user
            if user.is_blocked:
                msg = _reply_message(event)
                if msg:
                    try:
                        await msg.answer("دسترسی شما مسدود شده است.")
                    except Exception:
                        pass
                cq = event.callback_query if isinstance(event, Update) else (
                    event if isinstance(event, CallbackQuery) else None
                )
                if cq is not None:
                    try:
                        await cq.answer("دسترسی شما مسدود شده است.", show_alert=True)
                    except Exception:
                        pass
                return None
        return await handler(event, data)


class ErrorLogMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            if _is_benign_telegram_error(e):
                logger.debug("Ignored benign Telegram error: %s", e)
                return None
            logger.exception("Unhandled bot error")
            msg = _reply_message(event)
            if msg:
                try:
                    await msg.answer("خطایی رخ داد. لطفاً دوباره /start را بزنید.")
                except Exception:
                    pass
            # do not re-raise so polling keeps running
            return None
