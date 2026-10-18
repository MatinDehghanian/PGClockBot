"""Unfold the menu keyboard again when a typed reply ends a form.

Typing folds the bot's reply keyboard and only a new message carrying it unfolds it; editing
a message cannot. So when a typed reply takes the conversation out of its input state and
nothing in that update sent the menu keyboard, one short «منوی اصلی» message brings it back.
With chat cleanup on, the previous such message is deleted once the new one is in place, so
they never pile up. Welcome and other menu messages are never touched.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.client.session.middlewares.base import NextRequestMiddlewareType
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.methods import TelegramMethod
from aiogram.types import Message, ReplyKeyboardMarkup, TelegramObject

from app.bot.chat_cleanup import ChatKey, chat_key, delete_messages, is_cleanup_on
from app.bot.menu_nav import build_main_reply_keyboard, is_user_preview_active
from app.bot.reply_keyboard_state import take_keyboard_folded, was_typed
from app.services.users import get_all_settings

logger = logging.getLogger(__name__)

MENU_REOPEN_TEXT = "منوی اصلی"
SPARE_MENU_CHATS = 20_000


@dataclass(slots=True)
class _UpdateSends:
    menu_keyboard: bool = False


_sends: ContextVar[_UpdateSends | None] = ContextVar("menu_keyboard_sends", default=None)
# The last «منوی اصلی» message sent here per chat; only these are ever replaced.
_spare_menus: OrderedDict[ChatKey, int] = OrderedDict()


async def _watch_menu_keyboards(
    make_request: NextRequestMiddlewareType[Any], bot: Bot, method: TelegramMethod[Any]
) -> Any:
    result = await make_request(bot, method)
    sends = _sends.get()
    if sends is not None and isinstance(getattr(method, "reply_markup", None), ReplyKeyboardMarkup):
        sends.menu_keyboard = True
    return result


def install_menu_keyboard_watch(bot: Bot) -> Bot:
    """Let the bot report when an update already sent the menu keyboard."""
    bot.session.middleware(_watch_menu_keyboards)
    return bot


class MenuKeyboardReopenMiddleware(BaseMiddleware):
    """After a typed reply that ended a form, unfold the menu keyboard if nothing else did."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        state: FSMContext | None = data.get("state")
        if not isinstance(event, Message) or state is None:
            return await handler(event, data)
        was_in_form = await state.get_state() is not None
        sends = _UpdateSends()
        token = _sends.set(sends)
        try:
            result = await handler(event, data)
        finally:
            _sends.reset(token)
        if was_in_form and not sends.menu_keyboard and await state.get_state() is None:
            await _reopen_if_folded(event, state, data)
        return result


async def _reopen_if_folded(message: Message, state: FSMContext, data: dict[str, Any]) -> None:
    session, db_user = data.get("session"), data.get("db_user")
    if session is None or db_user is None or chat_key(message) is None:
        return
    if not was_typed(message, await get_all_settings(session)) or not await take_keyboard_folded(state):
        return
    try:
        markup, _ui, _role = await build_main_reply_keyboard(
            session,
            db_user,
            is_reseller_bot=bool(data.get("is_reseller_bot")),
            reseller_owner_id=data.get("reseller_owner_id"),
            as_user=await is_user_preview_active(state),
        )
        sent = await message.answer(MENU_REOPEN_TEXT, reply_markup=markup)
    except TelegramAPIError:
        logger.warning("could not reopen the menu keyboard", exc_info=True)
        return
    await _replace_spare_menu(sent)


async def _replace_spare_menu(sent: Message) -> None:
    """Remember the new «منوی اصلی» message; delete the previous one, which the new one replaces."""
    key = chat_key(sent)
    if key is None:
        return
    previous = _spare_menus.pop(key, None)
    _spare_menus[key] = int(sent.message_id)
    while len(_spare_menus) > SPARE_MENU_CHATS:
        _spare_menus.popitem(last=False)
    if previous is not None and is_cleanup_on():
        await delete_messages(sent.bot, key[1], [previous])
