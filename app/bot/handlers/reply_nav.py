"""Reply-keyboard main navigation — opens sections; selections stay as inline under messages."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import BaseFilter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.db.models import BotUser, Role, UserService
from app.services.formatting import format_message
from app.services.users import get_all_settings

router = Router(name="reply_nav")


class _SoftCallback:
    """Duck-typed CallbackQuery so admin handlers can edit a bot-owned message."""

    def __init__(self, message: Message, data: str):
        self.id = "reply"
        self.from_user = message.from_user
        self.message = message
        self.data = data
        self.bot = message.bot

    async def answer(self, *args, **kwargs):
        return True


class ReplyMenuTextFilter(BaseFilter):
    """Match only when the text is a known reply-menu label for this user."""

    async def __call__(
        self,
        message: Message,
        session: AsyncSession,
        db_user: BotUser,
        state: FSMContext,
        is_reseller_bot: bool = False,
        reseller_owner_id: int | None = None,
    ) -> bool | dict:
        text = (message.text or "").strip()
        if not text or kb.is_cancel_text(text):
            return False
        # Restart is handled by start.cmd_restart — avoid double handling
        if kb.is_restart_text(text):
            return False
        ui, role, has, show_creds = await _nav_context(
            session,
            db_user,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
        mapping = kb.reply_action_map(
            role,
            has_services=has,
            ui=ui,
            show_reseller_creds=show_creds,
        )
        if role == "admin":
            for k, v in kb.reply_action_map(
                "user",
                has_services=has,
                ui=ui,
                as_user=True,
            ).items():
                mapping.setdefault(k, v)
        # Home label (btn_menu_home) may differ from BTN_RESTART
        home_label = (ui.get("btn_menu_home") or "").strip()
        if home_label and text == home_label:
            action = kb.REPLY_ACTION_HOME
        else:
            action = mapping.get(text)
        if not action:
            return False
        return {
            "reply_action": action,
            "reply_ui": ui,
            "reply_role": role,
        }


async def _has_services(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(
        select(UserService.id).where(UserService.bot_user_id == user_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _nav_context(
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool,
    reseller_owner_id: int | None,
) -> tuple[dict, str, bool, bool]:
    from app.services.reseller_access import effective_menu_role, is_shop_owner_on_main_bot

    ui = await get_all_settings(session)
    role = await effective_menu_role(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    has = await _has_services(session, db_user.id)
    show_creds = is_shop_owner_on_main_bot(db_user, is_reseller_bot=is_reseller_bot)
    return ui, role, has, show_creds


async def open_shop_list(
    message: Message, session: AsyncSession, db_user: BotUser, state: FSMContext
) -> None:
    from app.bot.handlers.shop import _custom_available_for_users
    from app.services.orders import list_active_plans
    from app.services.users import on

    await state.clear()
    ui = await get_all_settings(session)
    trial_on = on(ui.get("trial_enabled"))
    plans = await list_active_plans(session, include_trial=True)
    if not trial_on:
        plans = [p for p in plans if not p.is_trial]
    has_svc = (
        await session.execute(
            select(UserService.id).where(UserService.bot_user_id == db_user.id).limit(1)
        )
    ).scalar_one_or_none()
    if has_svc:
        plans = [p for p in plans if not p.is_trial]
    custom_on = await _custom_available_for_users(session, ui, plans=plans)
    wholesale_on = on(ui.get("wholesale_enabled")) and any(not p.is_trial for p in plans)
    if not plans and not custom_on:
        text = format_message(
            "🛒 فروشگاه",
            ui.get("shop_empty_text") or "در حال حاضر پلنی برای فروش فعال نیست.",
        )
        await message.answer(text, reply_markup=kb.back_home(ui))
        return
    await message.answer(
        format_message("🛒 انتخاب پلن", "یکی از پلن‌ها را انتخاب کنید:"),
        reply_markup=kb.plans_keyboard(
            plans, ui, custom_enabled=custom_on, wholesale_enabled=wholesale_on
        ),
    )


async def open_services_list(message: Message, session: AsyncSession, db_user: BotUser) -> None:
    ui = await get_all_settings(session)
    result = await session.execute(
        select(UserService)
        .where(UserService.bot_user_id == db_user.id)
        .order_by(UserService.id.desc())
    )
    services = list(result.scalars().all())
    if not services:
        await message.answer(
            ui.get("empty_services_text")
            or "هنوز سرویسی ندارید.\nاز بخش «خرید سرویس» شروع کنید.",
            reply_markup=kb.back_home(ui),
        )
        return
    await message.answer(
        "📦 <b>سرویس‌های شما</b>",
        reply_markup=kb.services_keyboard(services, ui),
    )


async def open_wallet_home(message: Message, session: AsyncSession, db_user: BotUser) -> None:
    from app.config import get_settings
    from app.services.formatting import format_toman, kv_line

    ui = await get_all_settings(session)
    text = format_message(
        "👛 کیف پول",
        "\n".join(
            [
                kv_line(
                    "💵",
                    "موجودی",
                    f"<b>{format_toman(db_user.wallet_balance, get_settings().currency)}</b>",
                ),
            ]
        ),
    )
    await message.answer(text, reply_markup=kb.wallet_keyboard(ui))


async def open_support_home(message: Message, session: AsyncSession) -> None:
    from app.services.support_contacts import (
        active_support_contacts,
        parse_support_contacts,
        support_chat_url,
    )

    ui = await get_all_settings(session)
    contacts = active_support_contacts(parse_support_contacts(ui.get("support_contacts")))
    if len(contacts) == 1:
        url = support_chat_url(contacts[0].get("telegram") or "")
        title = contacts[0].get("title") or "پشتیبان"
        rows: list[list[InlineKeyboardButton]] = []
        if url:
            rows.append([InlineKeyboardButton(text=f"💬 گفتگو با {title}", url=url)])
        rows.append(
            [InlineKeyboardButton(text="🟣✉️ تیکت پشتیبانی", callback_data="support:tickets")]
        )
        rows.append(
            [InlineKeyboardButton(text=ui.get("btn_back") or "بازگشت", callback_data="menu:home")]
        )
        text = format_message(
            "🎧 پشتیبانی",
            f"برای ارتباط مستقیم روی دکمه زیر بزنید:\n<b>{title}</b>",
        )
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return
    if len(contacts) > 1:
        await message.answer(
            format_message("🎧 پشتیبانی", "یکی از پشتیبان‌ها را انتخاب کنید:"),
            reply_markup=kb.support_contacts_keyboard(contacts, ui),
        )
        return
    text = ui.get("support_text") or "پیام خود را بنویسید؛ تیم پشتیبانی پاسخ می‌دهد."
    await message.answer(
        format_message("🎧 پشتیبانی", text),
        reply_markup=kb.support_keyboard(ui),
    )


async def open_guide(message: Message, session: AsyncSession) -> None:
    ui = await get_all_settings(session)
    body = (ui.get("guide_text") or "").strip() or (
        "متنی برای راهنما تنظیم نشده. از وب‌پنل → تنظیمات ربات → متن‌ها، فیلد «متن راهنما» را پر کنید."
    )
    await message.answer(format_message("📘 راهنما", body), reply_markup=kb.back_home(ui))


async def open_faq(message: Message, session: AsyncSession) -> None:
    ui = await get_all_settings(session)
    await message.answer(
        format_message("❓ سوالات متداول", ui.get("faq_text") or ""),
        reply_markup=kb.back_home(ui),
    )


async def open_referral(message: Message, session: AsyncSession, db_user: BotUser) -> None:
    from app.config import get_settings

    ui = await get_all_settings(session)
    me = await message.bot.get_me()
    uname = me.username or get_settings().bot_username or "bot"
    link = f"https://t.me/{uname}?start=ref_{db_user.referral_code}"
    try:
        body = ui["referral_text"].format(code=db_user.referral_code, link=link)
    except Exception:
        body = f"کد: {db_user.referral_code}\n{link}"
    await message.answer(
        format_message("🎁 دعوت دوستان", body),
        reply_markup=kb.back_home(ui),
    )


async def open_reseller_apply(message: Message, session: AsyncSession, db_user: BotUser) -> None:
    from app.config import get_settings
    from app.services.formatting import format_toman
    from app.services.resellers import list_active_reseller_plans

    ui = await get_all_settings(session)
    order_keys = [p.strip() for p in (ui.get("menu_order") or "").split(",") if p.strip()]
    if "reseller_apply" not in order_keys:
        await message.answer("درخواست نمایندگی در منو فعال نیست.")
        return
    if db_user.role == Role.RESELLER.value:
        await message.answer("شما هم‌اکنون نماینده هستید.")
        return
    if db_user.role == Role.ADMIN.value:
        await message.answer("ادمین نیاز به درخواست ندارد.")
        return
    plans = await list_active_reseller_plans(session)
    if not plans:
        await message.answer(
            format_message(
                "🤝 نمایندگی",
                "در حال حاضر پلن نمایندگی فعالی تعریف نشده است.\nبعداً دوباره بررسی کنید.",
            ),
            reply_markup=kb.back_home(ui),
        )
        return
    rows = []
    for p in plans:
        price = format_toman(p.price, get_settings().currency) if p.price else "رایگان"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{p.name} — {price}",
                    callback_data=f"resapply:plan:{p.id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=ui.get("btn_back") or "بازگشت", callback_data="menu:home")]
    )
    await message.answer(
        format_message(
            "🤝 درخواست نمایندگی",
            "یکی از پلن‌های زیر را انتخاب کنید. پس از پرداخت (در صورت نیاز) ادمین درخواست را بررسی می‌کند.",
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def open_reseller_home(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool,
    reseller_owner_id: int | None,
) -> None:
    from app.services.reseller_access import load_reseller_actor

    if not is_reseller_bot:
        await open_reseller_creds(message, session, db_user)
        return
    owner_id, profile = await load_reseller_actor(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if not owner_id or not profile:
        await message.answer("دسترسی نماینده یافت نشد.")
        return
    await message.answer(
        format_message("🤝 پنل نماینده", "دسترسی‌ها با وب‌پنل یکسان است."),
        reply_markup=kb.reseller_home(profile),
    )


async def open_reseller_creds(message: Message, session: AsyncSession, db_user: BotUser) -> None:
    from app.services.resellers import format_reseller_access_card, get_reseller_profile

    if db_user.role != Role.RESELLER.value:
        await message.answer("فقط نمایندگان.")
        return
    profile = await get_reseller_profile(session, db_user.id)
    if not profile or not profile.is_active:
        await message.answer("پروفایل نماینده یافت نشد.")
        return
    text = await format_reseller_access_card(session, profile)
    rows = [[InlineKeyboardButton(text="⬅️ بازگشت", callback_data="menu:home")]]
    if profile.bot_username:
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    text=f"باز کردن @{profile.bot_username}",
                    url=f"https://t.me/{profile.bot_username}",
                )
            ],
        )
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def open_admin_home(message: Message, db_user: BotUser) -> None:
    from app.version import __version__ as local_version

    if db_user.role != Role.ADMIN.value:
        await message.answer("ادمین نیستید.")
        return
    await message.answer(
        f"🛠 <b>پنل ادمین</b>\n<code>v{local_version}</code>\n\n"
        "از منوی زیر یا کیبورد پایین بخش موردنظر را انتخاب کنید.",
        reply_markup=kb.admin_home(),
    )


async def open_user_preview(message: Message, session: AsyncSession, db_user: BotUser) -> None:
    ui = await get_all_settings(session)
    has = await _has_services(session, db_user.id)
    text = format_message(
        "👁 پیش‌نمایش منوی کاربر",
        "کیبورد پایین به حالت کاربر تغییر کرد. برای بازگشت «منوی اصلی» را بزنید.",
    )
    await message.answer(
        text,
        reply_markup=kb.main_reply_keyboard(
            db_user.role,
            has_services=has,
            ui=ui,
            as_user=True,
        ),
    )


async def _soft_admin(message: Message, session: AsyncSession, db_user: BotUser, data: str) -> None:
    from app.bot.handlers import admin as admin_h

    if db_user.role != Role.ADMIN.value:
        await message.answer("ادمین نیستید.")
        return
    bubble = await message.answer("⏳")
    cb = _SoftCallback(bubble, data)
    if data == "adm:orders":
        await admin_h.adm_orders(cb, session, db_user)
    elif data == "adm:payments":
        await admin_h.adm_payments(cb, session, db_user)
    elif data == "adm:tickets":
        await admin_h.adm_tickets(cb, session, db_user)
    elif data == "adm:plans":
        await admin_h.adm_plans(cb, session, db_user)
    elif data == "adm:pg":
        await admin_h.adm_pg(cb, db_user)


@router.message(StateFilter(None), F.text, ReplyMenuTextFilter())
async def reply_main_nav(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    reply_action: str,
    reply_ui: dict,
    reply_role: str,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    """Handle taps on the persistent reply keyboard (only when no FSM state)."""
    from app.bot.handlers.start import render_home

    action = reply_action
    ui = reply_ui
    role = reply_role

    if action == kb.REPLY_ACTION_HOME:
        await state.clear()
        await render_home(
            message,
            session,
            db_user,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
            ui=ui,
            effective_role=role,
        )
        return

    if action == kb.REPLY_ACTION_SHOP:
        await open_shop_list(message, session, db_user, state)
    elif action == kb.REPLY_ACTION_SERVICES:
        await open_services_list(message, session, db_user)
    elif action == kb.REPLY_ACTION_WALLET:
        await open_wallet_home(message, session, db_user)
    elif action == kb.REPLY_ACTION_SUPPORT:
        await open_support_home(message, session)
    elif action == kb.REPLY_ACTION_GUIDE:
        await open_guide(message, session)
    elif action == kb.REPLY_ACTION_FAQ:
        await open_faq(message, session)
    elif action == kb.REPLY_ACTION_REFERRAL:
        await open_referral(message, session, db_user)
    elif action == kb.REPLY_ACTION_RESELLER_APPLY:
        await open_reseller_apply(message, session, db_user)
    elif action == kb.REPLY_ACTION_RESELLER:
        await open_reseller_home(
            message,
            session,
            db_user,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
    elif action == kb.REPLY_ACTION_CREDS:
        await open_reseller_creds(message, session, db_user)
    elif action == kb.REPLY_ACTION_ADMIN:
        await open_admin_home(message, db_user)
    elif action == kb.REPLY_ACTION_ADMIN_PREVIEW:
        await open_user_preview(message, session, db_user)
    elif action == kb.REPLY_ACTION_ADMIN_ORDERS:
        await _soft_admin(message, session, db_user, "adm:orders")
    elif action == kb.REPLY_ACTION_ADMIN_PAYMENTS:
        await _soft_admin(message, session, db_user, "adm:payments")
    elif action == kb.REPLY_ACTION_ADMIN_TICKETS:
        await _soft_admin(message, session, db_user, "adm:tickets")
    elif action == kb.REPLY_ACTION_ADMIN_PLANS:
        await _soft_admin(message, session, db_user, "adm:plans")
    elif action == kb.REPLY_ACTION_ADMIN_PG:
        await _soft_admin(message, session, db_user, "adm:pg")
