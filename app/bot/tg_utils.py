"""Small Telegram helpers — avoid noisy errors after a successful reply."""
from __future__ import annotations

import logging
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("pgclock.bot")

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_bot_number_text(text: str | None) -> str:
    """Normalize Persian/Arabic digits and separators for int/float parsing."""
    raw = (text or "").strip().translate(_FA_DIGITS).translate(_AR_DIGITS)
    return raw.replace(",", "").replace("٬", "").replace(" ", "")


def parse_bot_int(text: str | None, *, default: int | None = None) -> int:
    raw = normalize_bot_number_text(text)
    if not raw:
        if default is not None:
            return default
        raise ValueError("empty")
    return int(raw)


def parse_bot_float(text: str | None, *, default: float | None = None) -> float:
    raw = normalize_bot_number_text(text).replace("٫", ".").replace("،", ".")
    if not raw:
        if default is not None:
            return default
        raise ValueError("empty")
    return float(raw)


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


async def seed_reply_keyboard(message: Message, reply_markup, *, tip: str = "·") -> None:
    """Attach a reply keyboard without leaving a lasting second bubble."""
    try:
        tip_msg = await message.answer(tip or "·", reply_markup=reply_markup)
    except Exception:
        logger.warning("Could not seed reply keyboard", exc_info=True)
        return
    try:
        await tip_msg.delete()
    except Exception:
        pass


async def seed_persistent_reply_kb(message: Message) -> None:
    """Backward-compat: seed home-only reply keyboard."""
    from app.bot import keyboards as kb

    await seed_reply_keyboard(message, kb.persistent_reply_keyboard())


async def clear_fsm_with_reply(
    message: Message,
    state,
    *,
    note: str = "لغو شد.",
    session: AsyncSession | None = None,
    db_user=None,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> None:
    """Clear FSM and restore the full main reply keyboard when context is available."""
    from app.bot import keyboards as kb
    from app.bot.menu_nav import restore_main_reply

    if session is not None and db_user is not None:
        await restore_main_reply(
            message,
            session,
            db_user,
            text=note,
            state=state,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
        return
    await state.clear()
    await message.answer(note, reply_markup=kb.persistent_reply_keyboard())
