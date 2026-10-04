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
    send_kw: dict | None = None,
) -> bool:
    """Send a status message to the payer. Returns True on success.

    ``body`` may be a packed rich-text setting value (premium emoji). Callers
    may also pass prebuilt ``send_kw`` (entities / parse_mode) with a final
    plain ``body`` string.
    """
    if not user_id:
        return False
    user = await session.get(BotUser, int(user_id))
    if not user or not getattr(user, "telegram_id", None):
        return False
    try:
        from app.services.formatting import format_message
        from app.services.reseller_bots import open_notify_bot_for_user
        from app.services.rich_text import outbound_setting_text, unpack_rich_text

        if send_kw is not None:
            text = body
            kw = dict(send_kw)
        else:
            _, ents = unpack_rich_text(body)
            if ents:
                text, kw = outbound_setting_text(body, title=title)
            else:
                text = format_message(title, body)
                kw = {}

        bot, should_close = await open_notify_bot_for_user(session, user)
        try:
            msg_kw = {"parse_mode": "HTML", **kw}
            await bot.send_message(user.telegram_id, text, **msg_kw)
        finally:
            if should_close:
                await bot.session.close()
        return True
    except Exception:
        log.debug("notify_payer failed user_id=%s", user_id, exc_info=True)
        return False
