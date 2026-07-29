from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import SessionLocal
from app.services.reseller_bots import lookup_reseller_by_bot_token
from app.services.users import (
    get_or_create_user,
    reset_shop_reseller_id,
    set_shop_reseller_id,
)

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


async def check_force_join_member(bot: Bot, telegram_id: int, channel: str) -> bool | None:
    """Return True if member, False if left/kicked, None if membership cannot be verified.

    None means the channel/bot is misconfigured or Telegram errored — callers should
    not permanently lock users out on None.
    """
    chat_id = channel if str(channel).startswith("@") else channel
    try:
        member = await bot.get_chat_member(chat_id, int(telegram_id))
        status = getattr(member, "status", None)
        status_val = getattr(status, "value", status)
        if str(status_val) in {"left", "kicked"}:
            return False
        return True
    except Exception as exc:
        logger.warning("force-join membership check failed for %s: %s", channel, exc)
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
        bot: Bot | None = data.get("bot")
        reseller_owner_id: int | None = None
        reseller_profile_id: int | None = None
        is_reseller_bot = False

        token = getattr(bot, "token", None) if bot else None
        main_token = (get_settings().bot_token or "").strip()
        if token and main_token and token != main_token:
            info = await lookup_reseller_by_bot_token(session, token)
            if info:
                reseller_owner_id = int(info["user_id"])
                reseller_profile_id = int(info["profile_id"])
                is_reseller_bot = True

        data["reseller_owner_id"] = reseller_owner_id
        data["reseller_profile_id"] = reseller_profile_id
        data["is_reseller_bot"] = is_reseller_bot

        ctx_token = set_shop_reseller_id(reseller_owner_id)
        try:
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
                        reseller_owner_id=reseller_owner_id,
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
        finally:
            reset_shop_reseller_id(ctx_token)


class ForceJoinMiddleware(BaseMiddleware):
    """Block shop/pay actions until channel membership is verified (real API check)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        session: AsyncSession | None = data.get("session")
        bot: Bot | None = data.get("bot")
        db_user = data.get("db_user")
        if not session or not bot or not db_user:
            return await handler(event, data)

        # Always allow /start so the join prompt can be shown
        if _extract_start_payload(event) is not None or _is_bare_start(event):
            return await handler(event, data)

        from app.services.users import get_setting, on
        from app.services.reseller_access import effective_menu_role

        enabled = await get_setting(session, "force_join_enabled")
        channel = (await get_setting(session, "force_join_channel") or "").strip()
        if not on(enabled) or not channel:
            return await handler(event, data)

        role = await effective_menu_role(
            session,
            db_user,
            is_reseller_bot=bool(data.get("is_reseller_bot")),
            reseller_owner_id=data.get("reseller_owner_id"),
        )
        if role != "user":
            return await handler(event, data)

        joined = await check_force_join_member(bot, int(db_user.telegram_id), channel)
        if joined is False:
            msg = _reply_message(event)
            text = (
                f"برای ادامه، ابتدا در کانال {channel} عضو شوید، سپس دوباره /start بزنید."
            )
            if msg:
                try:
                    await msg.answer(text)
                except Exception:
                    pass
            cq = event.callback_query if isinstance(event, Update) else (
                event if isinstance(event, CallbackQuery) else None
            )
            if cq is not None:
                try:
                    await cq.answer("ابتدا در کانال عضو شوید", show_alert=True)
                except Exception:
                    pass
            return None
        # joined True or None (unverifiable) → allow through

        return await handler(event, data)


def _is_bare_start(event: TelegramObject) -> bool:
    text = None
    if isinstance(event, Message) and event.text:
        text = event.text.strip()
    elif isinstance(event, Update) and event.message and event.message.text:
        text = event.message.text.strip()
    if not text:
        return False
    return text.split()[0].startswith("/start")


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
