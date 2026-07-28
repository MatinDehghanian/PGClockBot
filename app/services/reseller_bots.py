"""Runtime manager for reseller-owned Telegram bots (multi-token polling)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonCommands
from sqlalchemy import select

from app.db.models import ResellerProfile
from app.db.session import SessionLocal

log = logging.getLogger(__name__)

_manager: "ResellerBotManager | None" = None


class ResellerBotManager:
    """Polls each reseller bot and feeds updates into the shared dispatcher."""

    def __init__(self, dispatcher: Dispatcher):
        self.dispatcher = dispatcher
        self._tasks: dict[int, asyncio.Task] = {}
        self._bots: dict[int, Bot] = {}
        self._lock = asyncio.Lock()

    async def start_all(self) -> None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ResellerProfile).where(
                    ResellerProfile.is_active.is_(True),
                    ResellerProfile.setup_completed_at.is_not(None),
                    ResellerProfile.bot_token.is_not(None),
                )
            )
            rows = list(result.scalars().all())
            items = [(r.id, r.bot_token, r.bot_telegram_id) for r in rows if r.bot_token]
        for rid, token, tg_id in items:
            try:
                await self.start_reseller(rid, token, bot_telegram_id=tg_id)
            except Exception:
                log.exception("Failed to start reseller bot profile_id=%s", rid)

    async def start_reseller(
        self,
        reseller_profile_id: int,
        token: str,
        bot_telegram_id: int | None = None,
    ) -> bool:
        token = (token or "").strip()
        if not token:
            return False
        async with self._lock:
            await self._stop_locked(reseller_profile_id)
            bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
            try:
                me = await bot.get_me()
                tg_id = int(me.id)
                uname = me.username or ""
                await bot.set_my_commands(
                    [
                        BotCommand(command="start", description="شروع / منو"),
                        BotCommand(command="help", description="راهنما"),
                    ]
                )
                try:
                    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
                except Exception:
                    pass
            except Exception as e:
                log.warning("reseller bot %s get_me failed: %s", reseller_profile_id, e)
                await bot.session.close()
                return False

            async with SessionLocal() as session:
                row = await session.get(ResellerProfile, reseller_profile_id)
                if row:
                    row.bot_telegram_id = tg_id
                    row.bot_username = uname
                    await session.commit()

            self._bots[reseller_profile_id] = bot
            task = asyncio.create_task(
                self._poll_loop(reseller_profile_id, bot),
                name=f"reseller-bot-{reseller_profile_id}",
            )
            self._tasks[reseller_profile_id] = task
            log.info("Started reseller bot profile=%s (@%s)", reseller_profile_id, uname)
            return True

    async def stop_reseller(self, reseller_profile_id: int) -> None:
        async with self._lock:
            await self._stop_locked(reseller_profile_id)

    async def stop_by_user_id(self, reseller_user_id: int) -> None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ResellerProfile.id).where(ResellerProfile.user_id == reseller_user_id)
            )
            pid = result.scalar_one_or_none()
        if pid is not None:
            await self.stop_reseller(int(pid))

    async def restart_reseller_profile(self, profile_id: int) -> bool:
        async with SessionLocal() as session:
            row = await session.get(ResellerProfile, profile_id)
            if not row or not row.bot_token or not row.is_active:
                return False
            token = row.bot_token
            tg_id = row.bot_telegram_id
        return await self.start_reseller(profile_id, token, bot_telegram_id=tg_id)

    async def _stop_locked(self, reseller_profile_id: int) -> None:
        task = self._tasks.pop(reseller_profile_id, None)
        bot = self._bots.pop(reseller_profile_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        if bot:
            try:
                await bot.session.close()
            except Exception:
                pass

    async def stop_all(self) -> None:
        async with self._lock:
            ids = list(self._tasks.keys())
            for rid in ids:
                await self._stop_locked(rid)

    async def _poll_loop(self, reseller_profile_id: int, bot: Bot) -> None:
        offset: int | None = None
        try:
            try:
                await bot.delete_webhook(drop_pending_updates=True)
            except Exception:
                pass
            while True:
                try:
                    updates = await bot.get_updates(
                        offset=offset,
                        timeout=25,
                        allowed_updates=None,
                    )
                    for update in updates:
                        offset = update.update_id + 1
                        try:
                            await self.dispatcher.feed_update(bot, update)
                        except Exception:
                            log.exception(
                                "reseller bot %s failed to handle update %s",
                                reseller_profile_id,
                                getattr(update, "update_id", "?"),
                            )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning(
                        "reseller bot %s get_updates error: %s",
                        reseller_profile_id,
                        e,
                    )
                    await asyncio.sleep(3)
        finally:
            try:
                await bot.session.close()
            except Exception:
                pass

    def bot_for_token(self, token: str) -> Bot | None:
        for bot in self._bots.values():
            if bot.token == token:
                return bot
        return None

    def profile_id_for_bot(self, bot: Bot) -> int | None:
        for rid, b in self._bots.items():
            if b is bot or b.token == bot.token:
                return rid
        return None


def get_reseller_bot_manager() -> ResellerBotManager | None:
    return _manager


def init_reseller_bot_manager(dispatcher: Dispatcher) -> ResellerBotManager:
    global _manager
    _manager = ResellerBotManager(dispatcher)
    return _manager


async def lookup_reseller_by_bot_token(session, token: str) -> dict[str, Any] | None:
    """Resolve active reseller profile that owns this bot token."""
    token = (token or "").strip()
    if not token:
        return None
    result = await session.execute(
        select(ResellerProfile).where(
            ResellerProfile.bot_token == token,
            ResellerProfile.is_active.is_(True),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    return {
        "profile_id": row.id,
        "user_id": row.user_id,
        "bot_username": row.bot_username,
        "bot_telegram_id": row.bot_telegram_id,
    }


async def start_reseller_bot_for_profile(profile_id: int) -> bool:
    mgr = get_reseller_bot_manager()
    if not mgr:
        return False
    return await mgr.restart_reseller_profile(profile_id)
