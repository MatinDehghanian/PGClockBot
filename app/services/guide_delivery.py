"""Sending a connection guide's photos and videos to a Telegram chat."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo, Message

from app.services.guide_media import KIND_VIDEO, MediaToSend

logger = logging.getLogger(__name__)


def _album_item(item: MediaToSend) -> InputMediaPhoto | InputMediaVideo:
    source = item.file_id or FSInputFile(item.path)
    return InputMediaVideo(media=source) if item.kind == KIND_VIDEO else InputMediaPhoto(media=source)


def _sent_file_id(message: Message) -> str | None:
    if message.video:
        return message.video.file_id
    return message.photo[-1].file_id if message.photo else None


async def send_guide_album(bot: Bot, chat_id: int, album: list[MediaToSend]) -> dict[str, str]:
    """Send the guide's photos and videos; returns the file ids learned for uploaded files."""
    try:
        if len(album) == 1:
            item = album[0]
            source = item.file_id or FSInputFile(item.path)
            sent = [
                await (bot.send_video(chat_id, video=source) if item.kind == KIND_VIDEO else bot.send_photo(chat_id, photo=source))
            ]
        else:
            sent = await bot.send_media_group(chat_id, media=[_album_item(item) for item in album])
    except TelegramAPIError:
        logger.warning("guide album send failed chat_id=%s items=%s", chat_id, len(album), exc_info=True)
        return {}
    learned = {}
    for item, message in zip(album, sent, strict=False):
        file_id = _sent_file_id(message)
        if item.path is not None and file_id:
            learned[item.media_id] = file_id
    return learned

