"""Notify the paying end-user (Telegram) about payment/order status changes."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser

log = logging.getLogger(__name__)


async def notify_payer(
    session: AsyncSession,
    user_id: int | None,
    *,
    title: str,
    body: str,
) -> bool:
    """Send an HTML status message to the payer. Returns True on success."""
    if not user_id:
        return False
    user = await session.get(BotUser, int(user_id))
    if not user or not getattr(user, "telegram_id", None):
        return False
    try:
        from app.services.formatting import format_message
        from app.services.reseller_bots import open_notify_bot_for_user

        bot, should_close = await open_notify_bot_for_user(session, user)
        try:
            await bot.send_message(
                user.telegram_id,
                format_message(title, body),
                parse_mode="HTML",
            )
        finally:
            if should_close:
                await bot.session.close()
        return True
    except Exception:
        log.debug("notify_payer failed user_id=%s", user_id, exc_info=True)
        return False
