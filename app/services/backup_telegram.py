"""Send finished backups to Telegram: through the panel bot by default, or a separate backup bot."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.backup_settings import CHAT_IDS_KEY, TOKEN_KEY, parse_chat_ids
from app.services.secret_box import reveal_bot_token
from app.services.users import get_setting, on, set_setting

logger = logging.getLogger(__name__)

# Bot API upload limit for documents.
MAX_UPLOAD_BYTES = 49 * 1024 * 1024
UPLOAD_TIMEOUT_SECONDS = 300
STATUS_KEY = "backup_telegram_last_status"
STATUS_AT_KEY = "backup_telegram_last_at"


class BackupTelegramError(ValueError):
    """The destination is not usable; the message is safe to show to the admin."""


@dataclass(slots=True)
class Destination:
    token: str
    chat_ids: list[int]
    custom: bool


async def resolve_destination(session: AsyncSession) -> Destination:
    """Panel bot + main admins by default; the separate backup bot when that switch is on."""
    if on(await get_setting(session, "backup_telegram_custom_bot", "0")):
        token = reveal_bot_token(await get_setting(session, TOKEN_KEY, "")) or ""
        chat_ids = parse_chat_ids(await get_setting(session, CHAT_IDS_KEY, ""))
        if not token:
            raise BackupTelegramError("توکن ربات بکاپ ثبت نشده است.")
        if not chat_ids:
            raise BackupTelegramError("شناسهٔ چت گیرنده برای ربات بکاپ ثبت نشده است.")
        return Destination(token, chat_ids, custom=True)
    settings = get_settings()
    token = (settings.bot_token or "").strip()
    chat_ids = [int(chat_id) for chat_id in settings.admin_ids]
    if not token:
        raise BackupTelegramError("توکن ربات پنل تنظیم نشده است.")
    if not chat_ids:
        raise BackupTelegramError("هیچ ادمین اصلی برای دریافت بکاپ تنظیم نشده است.")
    return Destination(token, chat_ids, custom=False)


def _open_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=None))


async def _record(session: AsyncSession, status: str) -> None:
    from datetime import datetime, timezone

    await set_setting(session, STATUS_KEY, status[:200])
    await set_setting(session, STATUS_AT_KEY, datetime.now(timezone.utc).isoformat())
    await session.commit()


async def send_backup(session: AsyncSession, path: Path, *, include_env: bool, caption: str) -> str:
    """Deliver one backup if the switch is on; returns a short status and stores it for the settings page.

    A backup that contains ``.env`` is never sent: it holds every token and secret.
    """
    if not on(await get_setting(session, "backup_telegram_enabled", "0")):
        return "disabled"
    if include_env:
        await _record(session, "skipped: بکاپ شامل .env است و برای تلگرام ارسال نمی‌شود")
        return "skipped"
    try:
        size = (await asyncio.to_thread(path.stat)).st_size
    except OSError:
        await _record(session, "error: فایل بکاپ پیدا نشد")
        return "error"
    if size > MAX_UPLOAD_BYTES:
        await _record(session, "skipped: حجم بکاپ از ۵۰ مگابایت بیشتر است و تلگرام آن را نمی‌پذیرد")
        return "skipped"
    try:
        destination = await resolve_destination(session)
    except BackupTelegramError as exc:
        await _record(session, f"error: {exc}")
        return "error"
    bot = _open_bot(destination.token)
    delivered = 0
    try:
        for chat_id in destination.chat_ids:
            try:
                await bot.send_document(
                    chat_id, FSInputFile(path), caption=caption[:900], request_timeout=UPLOAD_TIMEOUT_SECONDS
                )
                delivered += 1
            except TelegramAPIError:
                logger.warning("backup delivery failed chat=%s", chat_id, exc_info=True)
    finally:
        await bot.session.close()
    if delivered:
        await _record(session, f"ok: برای {delivered} گیرنده ارسال شد")
        return "ok"
    await _record(session, "error: ارسال به هیچ گیرنده‌ای ممکن نشد؛ ربات را در چت گیرنده شروع کنید و شناسه را بررسی کنید")
    return "error"


async def send_test_message(session: AsyncSession) -> int:
    """Send a short message to every recipient; returns how many received it."""
    destination = await resolve_destination(session)
    bot = _open_bot(destination.token)
    delivered = 0
    try:
        for chat_id in destination.chat_ids:
            try:
                await bot.send_message(chat_id, "✅ ارسال بکاپ به این گفتگو فعال است.")
                delivered += 1
            except TelegramAPIError:
                logger.warning("backup test message failed chat=%s", chat_id, exc_info=True)
    finally:
        await bot.session.close()
    return delivered
