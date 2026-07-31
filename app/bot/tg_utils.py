"""Small Telegram helpers — avoid noisy errors after a successful reply."""
from __future__ import annotations

import logging
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

logger = logging.getLogger("pgclock.bot")


def _is_not_modified(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "message is not modified" in text or "message to edit not found" in text


async def safe_edit_text(
    message: Message | None,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs: Any,
) -> bool:
    """edit_text that ignores benign Telegram errors. Returns True if edited."""
    if message is None:
        return False
    try:
        await message.edit_text(text, reply_markup=reply_markup, **kwargs)
        return True
    except TelegramBadRequest as e:
        if _is_not_modified(e):
            return False
        logger.warning("edit_text failed: %s", e)
        try:
            await message.answer(text, reply_markup=reply_markup, **kwargs)
            return True
        except Exception:
            logger.exception("fallback answer after edit_text failed")
            return False
    except Exception:
        logger.exception("edit_text unexpected error")
        try:
            await message.answer(text, reply_markup=reply_markup, **kwargs)
            return True
        except Exception:
            return False


async def seed_persistent_reply_kb(message: Message) -> None:
    """Attach «شروع مجدد» reply keyboard without a lasting second bubble.

    Must never raise after the real home message was already sent.
    """
    from app.bot import keyboards as kb

    try:
        tip = await message.answer("·", reply_markup=kb.persistent_reply_keyboard())
    except Exception:
        logger.warning("Could not seed reply keyboard", exc_info=True)
        return
    try:
        await tip.delete()
    except Exception:
        pass


async def clear_fsm_with_reply(message: Message, state, *, note: str = "لغو شد.") -> None:
    """Clear FSM and replace sticky انصراف keyboard with persistent شروع مجدد."""
    from app.bot import keyboards as kb

    await state.clear()
    await message.answer(note, reply_markup=kb.persistent_reply_keyboard())
