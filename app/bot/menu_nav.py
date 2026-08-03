"""Shared helpers to build / restore the persistent reply keyboard menu."""

from __future__ import annotations

from aiogram.types import Message, ReplyKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.db.models import BotUser, UserService
from app.services.users import get_all_settings


async def user_has_services(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(
        select(UserService.id).where(UserService.bot_user_id == user_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def build_main_reply_keyboard(
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
    as_user: bool = False,
    ui: dict | None = None,
) -> tuple[ReplyKeyboardMarkup, dict, str]:
    """Return (markup, ui, effective_role) for the main reply keyboard."""
    from app.services.reseller_access import effective_menu_role, is_shop_owner_on_main_bot

    if ui is None:
        ui = await get_all_settings(session)
    role = await effective_menu_role(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    has = False if (role == "admin" and not as_user) else await user_has_services(session, db_user.id)
    show_creds = is_shop_owner_on_main_bot(db_user, is_reseller_bot=is_reseller_bot)
    markup = kb.main_reply_keyboard(
        role,
        has_services=has,
        ui=ui,
        as_user=as_user,
        show_reseller_creds=show_creds,
    )
    return markup, ui, role


async def restore_main_reply(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    *,
    text: str = "🏠 منوی اصلی",
    state=None,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
    as_user: bool = False,
) -> dict:
    """Clear FSM (if any) and send a message that restores the main reply keyboard."""
    if state is not None:
        try:
            await state.clear()
        except Exception:
            pass
    markup, ui, role = await build_main_reply_keyboard(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
        as_user=as_user,
    )
    await message.answer(text, reply_markup=markup)
    return ui
