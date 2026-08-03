"""Telegram chat menu button helpers — hide the side Menu next to the input."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import MenuButtonDefault

log = logging.getLogger("pgclock.bot")


async def clear_telegram_menu_button(bot: Bot) -> None:
    """Remove BotFather-style Menu button beside the message composer.

    Keeps /start and /help working when typed; they are just not listed in the
    Telegram side menu.
    """
    try:
        await bot.delete_my_commands()
    except Exception:
        log.debug("delete_my_commands failed", exc_info=True)
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except Exception:
        log.debug("set_chat_menu_button(default) failed", exc_info=True)
    try:
        await bot.delete_chat_menu_button()
    except Exception:
        # Some Bot API builds only support set_chat_menu_button
        log.debug("delete_chat_menu_button failed", exc_info=True)
