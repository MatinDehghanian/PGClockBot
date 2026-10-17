"""Whether the person's menu keyboard is folded away, and how to tell a tap from typing.

Telegram folds the bot's reply keyboard (the four-square icon) as soon as the person opens
the phone keyboard to type, and only a new message carrying the reply keyboard unfolds it
again; editing a message cannot. The middleware below notes typed text in the FSM data so
the next return to the main menu can send the menu as a new message instead of an edit.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from app.bot import keyboards as kb
from app.services.rich_text import first_custom_emoji_id, is_button_label_key
from app.services.users import DEFAULT_SETTINGS, get_all_settings

logger = logging.getLogger(__name__)

KEYBOARD_FOLDED = "_reply_kb_folded"


def visible_button_labels(ui: dict[str, str]) -> set[str]:
    """Texts a menu button can send when tapped, with this bot's settings."""
    keys = {key for key in (*DEFAULT_SETTINGS, *ui) if is_button_label_key(key)}
    labels = {kb._t(ui, key).strip() for key in keys}
    labels |= {kb.BTN_BACK, kb.BTN_RESTART, kb._home_label(ui).strip(), kb._back_label(ui).strip()}
    labels.discard("")
    return labels


def is_menu_tap(message: Message, ui: dict[str, str]) -> bool:
    """A tap on a menu button sends exactly that button's text and never a premium emoji."""
    text = (message.text or "").strip()
    if not text or first_custom_emoji_id(message.entities):
        return False
    return text in visible_button_labels(ui)


def was_typed(message: Message, ui: dict[str, str]) -> bool:
    """Text the person typed in a private chat (not a command, not a menu tap)."""
    chat = getattr(message, "chat", None)
    text = (message.text or "").strip()
    if getattr(chat, "type", None) != "private" or not text or text.startswith("/"):
        return False
    return not is_menu_tap(message, ui)


async def take_keyboard_folded(state: FSMContext | None) -> bool:
    """Whether the keyboard was folded since the menu was last sent; clears the note."""
    if state is None:
        return False
    data = await state.get_data()
    if not data.get(KEYBOARD_FOLDED):
        return False
    await state.update_data({KEYBOARD_FOLDED: False})
    return True


class ReplyKeyboardStateMiddleware(BaseMiddleware):
    """Note typed text; never changes how the message itself is handled."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        state: FSMContext | None = data.get("state")
        session = data.get("session")
        if isinstance(event, Message) and state is not None and session is not None and event.text:
            try:
                if was_typed(event, await get_all_settings(session)) and not (await state.get_data()).get(KEYBOARD_FOLDED):
                    await state.update_data({KEYBOARD_FOLDED: True})
            except Exception:  # noqa: BLE001 - a missed note only means the next home is an edit
                logger.warning("could not note the folded menu keyboard", exc_info=True)
        return await handler(event, data)
