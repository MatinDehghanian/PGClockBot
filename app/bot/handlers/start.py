from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
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
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    *,
    edit: bool = False,
    seed_reply_kb: bool = False,
):
    from app.services.formatting import format_message

    ui = await get_all_settings(session)
    if db_user.role == "admin":
        text = format_message(
            f"🛠 {ui.get('shop_title', 'کلاک')}",
            "پنل مدیریت فروشگاه\nاز گزینه‌های زیر استفاده کنید.",
        )
        markup = kb.main_menu(db_user.role, has_services=False, ui=ui)
    else:
        welcome = ui.get("welcome_text", "")
        title = ui.get("shop_title", "")
        try:
            body = welcome.format(name=db_user.full_name or "دوست عزیز")
        except Exception:
            body = welcome
        text = format_message(f"✨ {title}", body)
        has = await _has_services(session, db_user.id)
        markup = kb.main_menu(db_user.role, has_services=has, ui=ui)
    if edit:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except Exception:
            pass

    # One message: welcome + inline menu (Telegram cannot mix reply+inline markups)
    await message.answer(text, reply_markup=markup)

    if seed_reply_kb:
        # Keep «شروع مجدد» on the reply keyboard without a second visible home message
        tip = await message.answer("\u200c", reply_markup=kb.persistent_reply_keyboard())
        try:
            await tip.delete()
        except Exception:
            pass


@router.message(F.text.func(kb.is_restart_text))
async def cmd_restart(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: BotUser,
):
    await state.clear()
    await render_home(message, session, db_user, seed_reply_kb=True)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
):
    await state.clear()
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
            f"برای استفاده، ابتدا در کانال {channel} عضو شوید سپس دوباره /start بزنید.",
            reply_markup=kb.persistent_reply_keyboard(),
        )
        return
    await render_home(message, session, db_user, seed_reply_kb=True)


@router.callback_query(F.data == "menu:home")
async def cb_home(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    if callback.message:
        await render_home(callback.message, session, db_user, edit=True)


@router.callback_query(F.data == "menu:as_user")
async def cb_home_as_user(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    """Admin preview of the customer menu."""
    from app.services.formatting import format_message

    await callback.answer()
    ui = await get_all_settings(session)
    has = await _has_services(session, db_user.id)
    markup = kb.main_menu(db_user.role, has_services=has, ui=ui, as_user=True)
    text = format_message("👁 پیش‌نمایش منوی کاربر", "این همان منویی است که مشتری می‌بیند.")
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=markup)
        except Exception:
            await callback.message.answer(text, reply_markup=markup)


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession, db_user: BotUser, state: FSMContext):
    await state.clear()
    await render_home(message, session, db_user, seed_reply_kb=True)


@router.callback_query(F.data == "help:guide")
async def help_guide(callback: CallbackQuery, session: AsyncSession):
    from app.services.formatting import format_message

    await callback.answer()
    ui = await get_all_settings(session)
    if callback.message:
        await callback.message.edit_text(
            format_message("📘 راهنما", ui.get("guide_text") or ""),
            reply_markup=kb.back_home(ui),
        )


@router.callback_query(F.data == "help:faq")
async def help_faq(callback: CallbackQuery, session: AsyncSession):
    from app.services.formatting import format_message

    await callback.answer()
    ui = await get_all_settings(session)
    if callback.message:
        await callback.message.edit_text(
            format_message("❓ سوالات متداول", ui.get("faq_text") or ""),
            reply_markup=kb.back_home(ui),
        )


@router.callback_query(F.data == "ref:home")
async def referral_home(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    from app.services.formatting import format_message

    await callback.answer()
    ui = await get_all_settings(session)
    me = await callback.bot.get_me()
    uname = me.username or get_settings().bot_username or "bot"
    link = f"https://t.me/{uname}?start=ref_{db_user.referral_code}"
    try:
        body = ui["referral_text"].format(code=db_user.referral_code, link=link)
    except Exception:
        body = f"کد: {db_user.referral_code}\n{link}"
    if callback.message:
        await callback.message.edit_text(
            format_message("🎁 دعوت دوستان", body),
            reply_markup=kb.back_home(ui),
        )


async def _link_subscription(
    message: Message, session: AsyncSession, db_user: BotUser, token: str
):
    from app.services.formatting import format_message

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
        sub_url = f"{pg.base_url.rstrip('/')}/sub/{token}"
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
        format_message("✅ اتصال سرویس", service_card(info)),
        reply_markup=kb.service_actions(svc.id, ui),
    )
