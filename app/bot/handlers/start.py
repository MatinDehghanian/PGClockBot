from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.tg_utils import safe_edit_text, seed_persistent_reply_kb
from app.config import get_settings
from app.db.models import BotUser, UserService
from app.services.formatting import service_card
from app.services.pasarguard import extract_sub_token, get_pg
from app.services.users import get_all_settings, on

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
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    from app.services.formatting import format_message
    from app.services.reseller_access import effective_menu_role

    ui = await get_all_settings(session)
    # Dedicated reseller bot: owner + bot_admin_ids → reseller panel;
    # platform admins/other resellers → shop user menu.
    # Main bot: bot_admin_ids stay normal users.
    effective_role = await effective_menu_role(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )

    if effective_role == "admin":
        text = format_message(
            f"🛠 {ui.get('shop_title', 'کلاک')}",
            "پنل مدیریت فروشگاه\nاز گزینه‌های زیر استفاده کنید.",
        )
        markup = kb.main_menu(effective_role, has_services=False, ui=ui)
    else:
        welcome = ui.get("welcome_text", "")
        title = ui.get("shop_title", "")
        try:
            body = welcome.format(name=db_user.full_name or "دوست عزیز")
        except Exception:
            body = welcome
        text = format_message(f"✨ {title}", body)
        has = await _has_services(session, db_user.id)
        markup = kb.main_menu(effective_role, has_services=has, ui=ui)

    if edit:
        from aiogram.exceptions import TelegramBadRequest

        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return
            # Legacy photo home messages cannot be edit_text'd — replace once
            if getattr(message, "photo", None):
                try:
                    await message.delete()
                except Exception:
                    pass
                await message.answer(text, reply_markup=markup)
                return
        except Exception:
            pass

    # One message: welcome + inline menu (Telegram cannot mix reply+inline markups)
    await message.answer(text, reply_markup=markup)

    if seed_reply_kb:
        await seed_persistent_reply_kb(message)


@router.message(F.text.func(kb.is_restart_text))
async def cmd_restart(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    await state.clear()
    await render_home(
        message,
        session,
        db_user,
        seed_reply_kb=True,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    await state.clear()
    args = (command.args or "").strip()
    if args.startswith("ref_"):
        await message.answer(
            "کد دعوت ثبت شد ✅" if db_user.referred_by_id else "به ربات خوش آمدید."
        )
    elif args.startswith("sub_"):
        token = args[4:].strip()
        await _link_subscription(
            message,
            session,
            db_user,
            token,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
        return
    ui = await get_all_settings(session)
    channels = []
    try:
        from app.services.users import parse_force_join_channels

        channels = parse_force_join_channels(ui.get("force_join_channel"))
    except Exception:
        ch = (ui.get("force_join_channel") or "").strip()
        channels = [ch] if ch else []
    enabled = ui.get("force_join_enabled")
    from app.bot.middlewares import check_force_join_all
    from app.services.reseller_access import effective_menu_role

    role_for_force = await effective_menu_role(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if on(enabled) and channels and role_for_force == "user":
        missing, _ = await check_force_join_all(
            message.bot, int(db_user.telegram_id), channels
        )
        if missing:
            listed = "\n".join(f"• {c}" for c in missing)
            await message.answer(
                "برای استفاده، ابتدا در همه کانال‌های زیر عضو شوید سپس دوباره /start بزنید:\n"
                f"{listed}",
                reply_markup=kb.persistent_reply_keyboard(),
            )
            return
    await render_home(
        message,
        session,
        db_user,
        seed_reply_kb=True,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )


@router.callback_query(F.data == "menu:home")
async def cb_home(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    await callback.answer()
    await state.clear()
    if callback.message:
        await render_home(
            callback.message,
            session,
            db_user,
            edit=True,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )


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
async def cmd_menu(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    await state.clear()
    await render_home(
        message,
        session,
        db_user,
        seed_reply_kb=True,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )


@router.message(Command("help"))
async def cmd_help(message: Message, session: AsyncSession):
    """Telegram /help menu command — same content as دکمه راهنما (guide_text in settings)."""
    from app.services.formatting import format_message

    ui = await get_all_settings(session)
    body = (ui.get("guide_text") or "").strip() or "متنی برای راهنما تنظیم نشده. از وب‌پنل → تنظیمات ربات → متن‌ها، فیلد «متن راهنما» را پر کنید."
    await message.answer(
        format_message("📘 راهنما", body),
        reply_markup=kb.back_home(ui),
    )


@router.message(F.text.func(kb.is_cancel_text))
async def orphan_cancel(message: Message, state: FSMContext):
    """When انصراف is pressed outside an FSM prompt, clear sticky cancel keyboard."""
    cur = await state.get_state()
    if cur:
        # Let state-specific handlers process cancel; if none do, still clear below next tick
        return
    await message.answer(
        "عملیاتی برای انصراف نیست.",
        reply_markup=kb.persistent_reply_keyboard(),
    )


@router.callback_query(F.data == "help:guide")
async def help_guide(callback: CallbackQuery, session: AsyncSession):
    from app.services.formatting import format_message

    await callback.answer()
    ui = await get_all_settings(session)
    body = (ui.get("guide_text") or "").strip() or "متنی برای راهنما تنظیم نشده. از وب‌پنل → تنظیمات ربات → متن‌ها، فیلد «متن راهنما» را پر کنید."
    if callback.message:
        await safe_edit_text(
            callback.message,
            format_message("📘 راهنما", body),
            reply_markup=kb.back_home(ui),
        )


@router.callback_query(F.data == "help:faq")
async def help_faq(callback: CallbackQuery, session: AsyncSession):
    from app.services.formatting import format_message

    await callback.answer()
    ui = await get_all_settings(session)
    if callback.message:
        await safe_edit_text(
            callback.message,
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
        await safe_edit_text(
            callback.message,
            format_message("🎁 دعوت دوستان", body),
            reply_markup=kb.back_home(ui),
        )


async def _link_subscription(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    token: str,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    from app.services.formatting import format_message

    ui = await get_all_settings(session)
    pg = get_pg()
    try:
        info = await pg.subscription_info(token)
    except Exception:
        await message.answer("لینک نامعتبر است یا سرویس پیدا نشد.")
        await render_home(
            message,
            session,
            db_user,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
        return

    existing = await session.execute(
        select(UserService).where(
            UserService.bot_user_id == db_user.id,
            UserService.subscription_token == token,
        )
    )
    svc = existing.scalar_one_or_none()
    if not svc:
        claimed = await session.execute(
            select(UserService).where(
                UserService.subscription_token == token,
                UserService.bot_user_id != db_user.id,
            ).limit(1)
        )
        if claimed.scalar_one_or_none() is not None:
            await message.answer("این اشتراک قبلاً به حساب دیگری وصل شده است.")
            await render_home(
                message,
                session,
                db_user,
                is_reseller_bot=is_reseller_bot,
                reseller_owner_id=reseller_owner_id,
            )
            return
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
