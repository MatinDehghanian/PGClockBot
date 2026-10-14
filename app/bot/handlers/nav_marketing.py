"""Admin «بازاریابی» hub: the club and broadcast entries behind one group button.

The hub only lists leaves that already have their own handlers and guards
(``nv:adm:loy``, ``nv:adm:broadcast``); it never performs a send or a mutation.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import menu_nav as nav
from app.db.models import BotUser
from app.services.users import get_all_settings

router = Router(name="nav_marketing")

MARKETING_HUB_BODY = "🎯 <b>بازاریابی</b>\nباشگاه مشتریان و پیام گروهی."


async def open_admin_marketing_hub(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
    *,
    push: bool = True,
    is_reseller_bot: bool = False,
) -> None:
    # Local imports: reply_nav imports this module's dispatch targets, so a
    # module-level import would be circular.
    from app.bot.handlers.reply_nav import _deny_unless_owner
    from app.bot.nav_inline import admin_marketing_hub_keyboard, present_nav_panel

    if not await _deny_unless_owner(
        message, session, db_user, is_reseller_bot=is_reseller_bot
    ):
        return
    ui = await get_all_settings(session)
    if state is not None:
        await nav.set_nav_level(state, nav.NAV_ADMIN_MARKETING, push=push)
    await present_nav_panel(
        message,
        text=MARKETING_HUB_BODY,
        inline=admin_marketing_hub_keyboard(ui),
        state=state,
    )


@router.callback_query(F.data == "nv:adm:marketing")
async def nv_adm_marketing(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    is_reseller_bot: bool = False,
) -> None:
    await callback.answer()
    if not callback.message:
        return
    await open_admin_marketing_hub(
        callback.message,
        session,
        db_user,
        state,
        push=False,
        is_reseller_bot=is_reseller_bot,
    )
