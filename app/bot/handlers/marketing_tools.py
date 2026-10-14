"""Owner-only gift-code and campaign panels in the admin marketing hub.

Light operations only: list, enable/disable a code, start/pause a campaign. Creating
and editing stays in the web panel. Every action is an explicit target state on a
shop-scoped service call, so a repeated tap changes nothing the second time.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.auth import require_bot_owner_handler
from app.bot.marketing_panels import (
    CAMPAIGN_ACTION_PATTERN,
    CAMPAIGN_PANEL_CALLBACK,
    GIFT_PANEL_CALLBACK,
    GIFT_SET_PATTERN,
    campaigns_panel,
    gift_codes_panel,
    panel_page_url,
)
from app.bot.tg_utils import safe_edit_text
from app.db.models import BotUser
from app.services.campaigns import (
    CAMPAIGN_LIST_LIMIT,
    campaign_progress_map,
    change_campaign_state,
    list_recent_campaigns,
)
from app.services.gift_codes import describe_code, list_gift_codes, set_gift_code_active
from app.services.users import get_all_settings

logger = logging.getLogger(__name__)
router = Router(name="marketing_tools")

# The hub is Owner-only and runs on the platform bot, so every call targets the platform shop.
PLATFORM_SHOP = None
GIFT_PANEL_LIMIT = 8
CAMPAIGN_NOT_FOUND = "کمپین یافت نشد یا وضعیت آن تغییر کرده است"
GIFT_NOT_FOUND = "کد یافت نشد"
DONE = "انجام شد"


async def _show_gift_panel(callback: CallbackQuery, session: AsyncSession) -> None:
    ui = await get_all_settings(session)
    codes = await list_gift_codes(session, shop_id=PLATFORM_SHOP, limit=GIFT_PANEL_LIMIT)
    details = {code.id: describe_code(code) for code in codes}
    text, markup = gift_codes_panel(codes, details, ui=ui, web_url=panel_page_url("/gift-codes"))
    await safe_edit_text(callback.message, text, reply_markup=markup)


async def _show_campaign_panel(callback: CallbackQuery, session: AsyncSession) -> None:
    ui = await get_all_settings(session)
    campaigns = await list_recent_campaigns(session, shop_id=PLATFORM_SHOP, limit=CAMPAIGN_LIST_LIMIT)
    progress = await campaign_progress_map(session, [campaign.id for campaign in campaigns])
    text, markup = campaigns_panel(campaigns, progress, ui=ui, web_url=panel_page_url("/campaigns"))
    await safe_edit_text(callback.message, text, reply_markup=markup)


@router.callback_query(F.data == GIFT_PANEL_CALLBACK)
@require_bot_owner_handler
async def open_gift_panel(callback: CallbackQuery, session: AsyncSession, db_user: BotUser) -> None:
    await callback.answer()
    await _show_gift_panel(callback, session)


@router.callback_query(F.data.regexp(GIFT_SET_PATTERN.pattern))
@require_bot_owner_handler
async def set_gift_state(callback: CallbackQuery, session: AsyncSession, db_user: BotUser) -> None:
    match = GIFT_SET_PATTERN.match(callback.data or "")
    if match is None:
        await callback.answer()
        return
    changed = await set_gift_code_active(
        session, int(match.group(1)), shop_id=PLATFORM_SHOP, active=match.group(2) == "1"
    )
    await callback.answer(DONE if changed else GIFT_NOT_FOUND, show_alert=not changed)
    await _show_gift_panel(callback, session)


@router.callback_query(F.data == CAMPAIGN_PANEL_CALLBACK)
@require_bot_owner_handler
async def open_campaign_panel(callback: CallbackQuery, session: AsyncSession, db_user: BotUser) -> None:
    await callback.answer()
    await _show_campaign_panel(callback, session)


@router.callback_query(F.data.regexp(CAMPAIGN_ACTION_PATTERN.pattern))
@require_bot_owner_handler
async def change_campaign(callback: CallbackQuery, session: AsyncSession, db_user: BotUser) -> None:
    match = CAMPAIGN_ACTION_PATTERN.match(callback.data or "")
    if match is None:
        await callback.answer()
        return
    try:
        await change_campaign_state(
            session, int(match.group(2)), shop_id=PLATFORM_SHOP, action=match.group(1)
        )
    except ValueError:
        await session.rollback()
        await callback.answer(CAMPAIGN_NOT_FOUND, show_alert=True)
    else:
        await callback.answer(DONE)
    await _show_campaign_panel(callback, session)
