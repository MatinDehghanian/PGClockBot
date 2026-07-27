from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import get_settings
from app.db.models import BotUser, UserService
from app.services.formatting import service_card
from app.services.pasarguard import extract_sub_token, get_pg
from app.services.users import get_all_settings, get_setting, on

router = Router(name="start")


async def _has_services(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(
        select(UserService.id).where(UserService.bot_user_id == user_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def render_home(
    message: Message, session: AsyncSession, db_user: BotUser, *, edit: bool = False
):
    ui = await get_all_settings(session)
    welcome = ui.get("welcome_text", "")
    title = ui.get("shop_title", "")
    try:
        text = welcome.format(name=db_user.full_name or "دوست عزیز")
    except Exception:
        text = welcome
    text = f"<b>{title}</b>\n\n{text}"
    has = await _has_services(session, db_user.id)
    markup = kb.main_menu(db_user.role, has_services=has, ui=ui)
    if edit and isinstance(message, Message):
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=markup)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    db_user: BotUser,
):
    args = (command.args or "").strip()
    if args.startswith("ref_"):
        await message.answer(
            "کد دعوت ثبت شد ✅" if db_user.referred_by_id else "به ربات خوش آمدید."
        )
    elif args.startswith("sub_"):
        token = args[4:].strip()
        await _link_subscription(message, session, db_user, token)
        return
    channel = await get_setting(session, "force_join_channel")
    enabled = await get_setting(session, "force_join_enabled")
    if on(enabled) and channel and db_user.role == "user":
        await message.answer(
            f"برای استفاده، ابتدا در کانال {channel} عضو شوید سپس دوباره /start بزنید."
        )
    await render_home(message, session, db_user)


@router.callback_query(F.data == "menu:home")
async def cb_home(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    if callback.message:
        await render_home(callback.message, session, db_user, edit=True)


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession, db_user: BotUser):
    await render_home(message, session, db_user)


@router.callback_query(F.data == "help:guide")
async def help_guide(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    ui = await get_all_settings(session)
    if callback.message:
        await callback.message.edit_text(ui["guide_text"], reply_markup=kb.back_home(ui))


@router.callback_query(F.data == "help:faq")
async def help_faq(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    ui = await get_all_settings(session)
    if callback.message:
        await callback.message.edit_text(ui["faq_text"], reply_markup=kb.back_home(ui))


@router.callback_query(F.data == "ref:home")
async def ref_home(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    ui = await get_all_settings(session)
    settings = get_settings()
    uname = settings.bot_username or "bot"
    link = f"https://t.me/{uname}?start=ref_{db_user.referral_code}"
    try:
        text = ui["referral_text"].format(code=db_user.referral_code, link=link)
    except Exception:
        text = f"کد: {db_user.referral_code}\n{link}"
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.back_home(ui))


async def _link_subscription(
    message: Message, session: AsyncSession, db_user: BotUser, token: str
):
    ui = await get_all_settings(session)
    pg = get_pg()
    try:
        info = await pg.subscription_info(token)
    except Exception:
        await message.answer("لینک نامعتبر است یا سرویس پیدا نشد.")
        await render_home(message, session, db_user)
        return

    existing = await session.execute(
        select(UserService).where(
            UserService.bot_user_id == db_user.id,
            UserService.subscription_token == token,
        )
    )
    svc = existing.scalar_one_or_none()
    if not svc:
        sub_url = f"{get_settings().pg_base_url.rstrip('/')}/sub/{token}"
        svc = UserService(
            bot_user_id=db_user.id,
            pg_user_id=info.get("id"),
            pg_username=info.get("username", "unknown"),
            subscription_url=sub_url,
            subscription_token=token or extract_sub_token(sub_url),
            remark="linked",
        )
        session.add(svc)
        await session.commit()

    await message.answer(
        "✅ سرویس به حساب شما متصل شد:\n\n" + service_card(info),
        reply_markup=kb.service_actions(svc.id, ui),
    )
