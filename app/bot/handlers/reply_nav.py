"""Reply-keyboard main + submenu navigation (3.6.0).

All navigation (including submenus + pay methods) uses the reply keyboard.
Every submenu has «بازگشت» (one level) and «منوی اصلی».
Inline under messages: plans, services list, approve/reject only.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot import menu_nav as nav
from app.bot.menu_nav import restore_main_reply, user_has_services
from app.db.models import BotUser, Order, Role, UserService
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
    """Match known reply-menu / submenu labels (works even during FSM — clears it)."""

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
            include_submenus=True,
        )
        if role == "admin":
            for k, v in kb.reply_action_map(
                "user",
                has_services=has,
                ui=ui,
                as_user=True,
                include_submenus=True,
            ).items():
                mapping.setdefault(k, v)
        # Pay vs topup share labels — resolve by current nav level
        level = await nav.get_nav_level(state)
        if level == nav.NAV_TOPUP_PAY:
            for key, label in kb._topup_method_entries(ui):
                mapping[(label or "").strip()] = key
        elif level == nav.NAV_PAY:
            for key, label in kb._pay_method_entries(ui):
                mapping[(label or "").strip()] = key
        if kb.is_home_text(text, ui):
            action = kb.REPLY_ACTION_HOME
        elif text in {kb._back_label(ui), kb.BTN_BACK}:
            action = kb.REPLY_ACTION_BACK
        else:
            action = mapping.get(text)
        if not action:
            return False
        return {
            "reply_action": action,
            "reply_ui": ui,
            "reply_role": role,
        }


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
    has = await user_has_services(session, db_user.id)
    show_creds = is_shop_owner_on_main_bot(db_user, is_reseller_bot=is_reseller_bot)
    return ui, role, has, show_creds


async def open_shop_list(
    message: Message, session: AsyncSession, db_user: BotUser, state: FSMContext
) -> None:
    from app.bot.handlers.shop import _custom_available_for_users
    from app.bot.menu_nav import build_main_reply_keyboard
    from app.services.orders import list_active_plans
    from app.services.users import on

    await state.clear()
    ui = await get_all_settings(session)
    trial_on = on(ui.get("trial_enabled"))
    plans = await list_active_plans(session, include_trial=True)
    if not trial_on:
        plans = [p for p in plans if not p.is_trial]
    has_svc = await user_has_services(session, db_user.id)
    if has_svc:
        plans = [p for p in plans if not p.is_trial]
    custom_on = await _custom_available_for_users(session, ui, plans=plans)
    wholesale_on = on(ui.get("wholesale_enabled")) and any(not p.is_trial for p in plans)
    main_kb, _, _ = await build_main_reply_keyboard(session, db_user)
    if not plans and not custom_on:
        text = format_message(
            "🛒 فروشگاه",
            ui.get("shop_empty_text") or "در حال حاضر پلنی برای فروش فعال نیست.",
        )
        await message.answer(text, reply_markup=main_kb)
        return
    # Keep main reply KB visible; plan picks are inline under the message
    await message.answer(
        format_message("🛒 انتخاب پلن", "یکی از پلن‌ها را انتخاب کنید:"),
        reply_markup=main_kb,
    )
    await message.answer(
        "📦 پلن‌ها:",
        reply_markup=kb.plans_keyboard(
            plans, ui, custom_enabled=custom_on, wholesale_enabled=wholesale_on
        ),
    )


async def open_services_list(message: Message, session: AsyncSession, db_user: BotUser) -> None:
    from app.bot.menu_nav import build_main_reply_keyboard

    ui = await get_all_settings(session)
    result = await session.execute(
        select(UserService)
        .where(UserService.bot_user_id == db_user.id)
        .order_by(UserService.id.desc())
    )
    services = list(result.scalars().all())
    main_kb, _, _ = await build_main_reply_keyboard(session, db_user)
    if not services:
        await message.answer(
            ui.get("empty_services_text")
            or "هنوز سرویسی ندارید.\nاز بخش «خرید سرویس» شروع کنید.",
            reply_markup=main_kb,
        )
        return
    await message.answer("📦 <b>سرویس‌های شما</b>", reply_markup=main_kb)
    await message.answer("یکی را انتخاب کنید:", reply_markup=kb.services_keyboard(services, ui))


async def open_wallet_home(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
    *,
    push: bool = True,
) -> None:
    from app.config import get_settings
    from app.services.formatting import format_toman, kv_line

    text = format_message(
        "👛 کیف پول",
        "\n".join(
            [
                kv_line(
                    "💵",
                    "موجودی",
                    f"<b>{format_toman(db_user.wallet_balance, get_settings().currency)}</b>",
                ),
                "",
                "از کیبورد پایین شارژ یا تراکنش‌ها را انتخاب کنید.",
            ]
        ),
    )
    await nav.show_nav_keyboard(
        message,
        session,
        db_user,
        nav.NAV_WALLET,
        text=text,
        state=state,
        push=push,
    )


async def open_wallet_topup(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    from app.services.users import on

    ui = await get_all_settings(session)
    can_topup = any(
        on(ui.get(k))
        for k in ("pay_card_enabled", "pay_gateway_enabled", "pay_crypto_enabled")
    )
    if not can_topup:
        await message.answer(
            "روش شارژ فعالی تنظیم نشده.",
            reply_markup=kb.wallet_reply_keyboard(ui),
        )
        return
    from app.bot.handlers.wallet import WalletStates

    await state.set_state(WalletStates.topup_amount)
    await message.answer(
        format_message("➕ شارژ کیف پول", "مبلغ شارژ را به تومان وارد کنید:"),
        reply_markup=kb.cancel_reply(ui),
    )


async def open_wallet_tx(message: Message, session: AsyncSession, db_user: BotUser) -> None:
    from app.config import get_settings
    from app.services.formatting import format_toman
    from app.services.wallet import list_transactions

    ui = await get_all_settings(session)
    txs = await list_transactions(session, db_user.id, limit=15)
    if not txs:
        await message.answer(
            "تراکنشی ثبت نشده.",
            reply_markup=kb.wallet_reply_keyboard(ui),
        )
        return
    lines = []
    for t in txs:
        sign = "+" if t.amount >= 0 else ""
        lines.append(
            f"{sign}{format_toman(t.amount, get_settings().currency)} — {t.reason}"
        )
    await message.answer(
        format_message("📜 تراکنش‌ها", "\n".join(lines)),
        reply_markup=kb.wallet_reply_keyboard(ui),
    )


async def open_support_home(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
    *,
    push: bool = True,
) -> None:
    from app.services.support_contacts import (
        active_support_contacts,
        parse_support_contacts,
        support_chat_url,
    )

    ui = await get_all_settings(session)
    contacts = active_support_contacts(parse_support_contacts(ui.get("support_contacts")))
    await nav.show_nav_keyboard(
        message,
        session,
        db_user,
        nav.NAV_SUPPORT,
        text=format_message(
            "🎧 پشتیبانی",
            ui.get("support_text")
            or "از کیبورد پایین تیکت جدید بسازید یا تیکت‌های قبلی را ببینید.",
        ),
        state=state,
        push=push,
    )
    if contacts:
        rows: list[list[InlineKeyboardButton]] = []
        for c in contacts:
            url = support_chat_url(c.get("telegram") or "")
            title = c.get("title") or "پشتیبان"
            if url:
                rows.append([InlineKeyboardButton(text=f"💬 گفتگو با {title}", url=url)])
        if rows:
            await message.answer(
                "ارتباط مستقیم:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )


async def open_support_new(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    from app.bot.handlers.support import SupportStates

    ui = await get_all_settings(session)
    await state.set_state(SupportStates.subject)
    await message.answer(
        "موضوع تیکت را بنویسید:",
        reply_markup=kb.cancel_reply(ui),
    )


async def open_support_list(
    message: Message, session: AsyncSession, db_user: BotUser
) -> None:
    from app.services.tickets import list_user_tickets

    ui = await get_all_settings(session)
    tickets = await list_user_tickets(session, db_user.id)
    if not tickets:
        await message.answer(
            "تیکتی ندارید.",
            reply_markup=kb.support_reply_keyboard(ui),
        )
        return
    rows = [
        [
            InlineKeyboardButton(
                text=f"#{t.id} — {(t.subject or '')[:28]}",
                callback_data=f"support:view:{t.id}",
            )
        ]
        for t in tickets[:20]
    ]
    await message.answer(
        "📋 تیکت‌های شما:",
        reply_markup=kb.support_reply_keyboard(ui),
    )
    await message.answer(
        "یکی را باز کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def open_referral(message: Message, session: AsyncSession, db_user: BotUser) -> None:
    from app.bot.menu_nav import build_main_reply_keyboard
    from app.config import get_settings

    ui = await get_all_settings(session)
    me = await message.bot.get_me()
    uname = me.username or get_settings().bot_username or "bot"
    link = f"https://t.me/{uname}?start=ref_{db_user.referral_code}"
    try:
        body = ui["referral_text"].format(code=db_user.referral_code, link=link)
    except Exception:
        body = f"کد: {db_user.referral_code}\n{link}"
    main_kb, _, _ = await build_main_reply_keyboard(session, db_user)
    await message.answer(
        format_message("🎁 دعوت دوستان", body),
        reply_markup=main_kb,
    )


async def open_reseller_apply(message: Message, session: AsyncSession, db_user: BotUser) -> None:
    from app.bot.menu_nav import build_main_reply_keyboard
    from app.config import get_settings
    from app.services.formatting import format_toman
    from app.services.resellers import list_active_reseller_plans

    ui = await get_all_settings(session)
    order_keys = [p.strip() for p in (ui.get("menu_order") or "").split(",") if p.strip()]
    main_kb, _, _ = await build_main_reply_keyboard(session, db_user)
    if "reseller_apply" not in order_keys:
        await message.answer("درخواست نمایندگی در منو فعال نیست.", reply_markup=main_kb)
        return
    if db_user.role == Role.RESELLER.value:
        await message.answer("شما هم‌اکنون نماینده هستید.", reply_markup=main_kb)
        return
    if db_user.role == Role.ADMIN.value:
        await message.answer("ادمین نیاز به درخواست ندارد.", reply_markup=main_kb)
        return
    plans = await list_active_reseller_plans(session)
    if not plans:
        await message.answer(
            format_message(
                "🤝 نمایندگی",
                "در حال حاضر پلن نمایندگی فعالی تعریف نشده است.\nبعداً دوباره بررسی کنید.",
            ),
            reply_markup=main_kb,
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
    await message.answer(
        format_message(
            "🤝 درخواست نمایندگی",
            "یکی از پلن‌های زیر را انتخاب کنید.",
        ),
        reply_markup=main_kb,
    )
    await message.answer(
        "پلن‌ها:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def open_reseller_home(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
    *,
    is_reseller_bot: bool,
    reseller_owner_id: int | None,
    push: bool = True,
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
    await nav.show_nav_keyboard(
        message,
        session,
        db_user,
        nav.NAV_RESELLER,
        text=format_message("🤝 پنل نماینده", "از کیبورد پایین بخش موردنظر را انتخاب کنید."),
        state=state,
        push=push,
        profile=profile,
    )


async def open_reseller_creds(message: Message, session: AsyncSession, db_user: BotUser) -> None:
    from app.bot.menu_nav import build_main_reply_keyboard
    from app.services.resellers import format_reseller_access_card, get_reseller_profile

    main_kb, _, _ = await build_main_reply_keyboard(session, db_user)
    if db_user.role != Role.RESELLER.value:
        await message.answer("فقط نمایندگان.", reply_markup=main_kb)
        return
    profile = await get_reseller_profile(session, db_user.id)
    if not profile or not profile.is_active:
        await message.answer("پروفایل نماینده یافت نشد.", reply_markup=main_kb)
        return
    text = await format_reseller_access_card(session, profile)
    rows: list[list[InlineKeyboardButton]] = []
    if profile.bot_username:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"باز کردن @{profile.bot_username}",
                    url=f"https://t.me/{profile.bot_username}",
                )
            ]
        )
    await message.answer(text, reply_markup=main_kb)
    if rows:
        await message.answer("لینک ربات:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def open_pg_home(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
    *,
    push: bool = True,
) -> None:
    if db_user.role != Role.ADMIN.value:
        await message.answer("ادمین نیستید.")
        return
    await nav.show_nav_keyboard(
        message,
        session,
        db_user,
        nav.NAV_ADMIN_PG,
        text=(
            "🖥 <b>عملیات پاسارگارد</b>\n"
            "از کیبورد پایین بخش موردنظر را انتخاب کنید."
        ),
        state=state,
        push=push,
    )


async def open_admin_users_hub(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
    *,
    push: bool = True,
) -> None:
    if db_user.role != Role.ADMIN.value:
        await message.answer("ادمین نیستید.")
        return
    from sqlalchemy import func
    from app.db.models import Order

    total = await session.scalar(select(func.count()).select_from(BotUser))
    blocked = await session.scalar(
        select(func.count()).select_from(BotUser).where(BotUser.is_blocked.is_(True))
    ) or 0
    orders = await session.scalar(select(func.count()).select_from(Order))
    await nav.show_nav_keyboard(
        message,
        session,
        db_user,
        nav.NAV_ADMIN_USERS,
        text=(
            "👥 <b>کاربران بات</b>\n\n"
            f"کل: {total}\n"
            f"مسدود: {blocked}\n"
            f"سفارش‌ها: {orders}\n\n"
            "از کیبورد پایین لیست یا جستجو را انتخاب کنید."
        ),
        state=state,
        push=push,
    )


async def open_admin_resellers_hub(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
    *,
    push: bool = True,
) -> None:
    if db_user.role != Role.ADMIN.value:
        await message.answer("ادمین نیستید.")
        return
    await nav.show_nav_keyboard(
        message,
        session,
        db_user,
        nav.NAV_ADMIN_RESELLERS,
        text="🤝 <b>نمایندگان</b>\nاز کیبورد پایین بخش موردنظر را انتخاب کنید.",
        state=state,
        push=push,
    )


async def open_admin_settings_hub(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
    *,
    push: bool = True,
) -> None:
    if db_user.role != Role.ADMIN.value:
        await message.answer("ادمین نیستید.")
        return
    await nav.show_nav_keyboard(
        message,
        session,
        db_user,
        nav.NAV_ADMIN_SETTINGS,
        text="⚙️ <b>تنظیمات</b>\nاز کیبورد پایین یک بخش را انتخاب کنید:",
        state=state,
        push=push,
    )


async def open_admin_home(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
    *,
    push: bool = True,
) -> None:
    from app.version import __version__ as local_version

    if db_user.role != Role.ADMIN.value:
        await message.answer("ادمین نیستید.")
        return
    await nav.show_nav_keyboard(
        message,
        session,
        db_user,
        nav.NAV_ADMIN,
        text=(
            f"🛠 <b>پنل ادمین</b>\n<code>v{local_version}</code>\n\n"
            "از کیبورد پایین بخش موردنظر را انتخاب کنید."
        ),
        state=state,
        push=push,
    )


async def open_user_preview(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
) -> None:
    await nav.show_nav_keyboard(
        message,
        session,
        db_user,
        nav.NAV_USER_PREVIEW,
        text=format_message(
            "👁 پیش‌نمایش منوی کاربر",
            "کیبورد پایین به حالت کاربر تغییر کرد. «بازگشت» یا «منوی اصلی» را بزنید.",
        ),
        state=state,
        push=True,
        as_user=True,
    )


async def _soft_admin(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    data: str,
    state: FSMContext | None = None,
) -> None:
    from app.bot.handlers import admin as admin_h
    from app.bot.handlers import admin_backup as backup_h
    from app.bot.handlers import admin_settings as settings_h

    if db_user.role != Role.ADMIN.value:
        await message.answer("ادمین نیستید.")
        return
    bubble = await message.answer("⏳")
    cb = _SoftCallback(bubble, data)
    try:
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
        elif data == "adm:pg:stats":
            await admin_h.pg_stats(cb, db_user)
        elif data == "adm:pg:nodes":
            await admin_h.pg_nodes(cb, db_user)
        elif data == "adm:pg:group":
            await admin_h.adm_pg_group_hint(cb, db_user)
        elif data == "adm:pg:template":
            await admin_h.adm_pg_template_hint(cb, db_user)
        elif data == "adm:pg:users":
            from app.bot.handlers import admin_pg_users as pg_users_h

            await pg_users_h.pg_users_list(cb, state, db_user)
        elif data == "adm:pg:search":
            from app.bot.handlers import admin_pg_users as pg_users_h

            await pg_users_h.pg_search_start(cb, state, db_user)
        elif data == "adm:pg:create":
            from app.bot.handlers import admin_pg_users as pg_users_h

            await pg_users_h.pg_create_menu(cb, state, db_user)
        elif data == "adm:users:list:0":
            await admin_h.adm_users_list(cb, session, db_user)
        elif data == "adm:users:search":
            await admin_h.adm_users_search_start(cb, state, db_user)
        elif data == "adm:users:webhint":
            await admin_h.adm_users_webhint(cb, db_user)
        elif data == "adm:resellers:list:0":
            await admin_h.adm_resellers_list(cb, session, db_user)
        elif data == "adm:resapp:list":
            await admin_h.adm_resapp_list(cb, session, db_user)
        elif data == "adm:resellers:add":
            await admin_h.adm_resellers_add(cb, state, db_user)
        elif data.startswith("adm:st:sec:"):
            from app.bot.handlers import admin_settings as settings_h

            await settings_h.settings_section(cb, session, db_user)
        elif data == "adm:dash":
            await admin_h.adm_dash(cb, session, db_user)
        elif data == "adm:resellers":
            await admin_h.adm_resellers(cb, db_user)
        elif data == "adm:backup":
            await backup_h.backup_hub(cb, db_user, state)
        elif data == "adm:broadcast":
            await bubble.edit_text(
                "📢 پیام گروهی:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="شروع پیام گروهی", callback_data="adm:broadcast")]
                    ]
                ),
            )
        elif data == "adm:settings":
            if state is not None:
                await settings_h.settings_hub(cb, state, db_user)
            else:
                await bubble.edit_text(
                    "⚙️ تنظیمات:",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="باز کردن تنظیمات", callback_data="adm:settings")]
                        ]
                    ),
                )
        else:
            await bubble.edit_text("این بخش در دسترس نیست.")
    except Exception as e:
        try:
            await bubble.edit_text(f"خطا: {e}")
        except Exception:
            pass


async def handle_back(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> None:
    """One-level back through the reply-keyboard stack."""
    data = await state.get_data()
    await state.set_state(None)
    await state.set_data(data)
    level = await nav.pop_nav_level(state)
    if level == nav.NAV_WALLET:
        await open_wallet_home(message, session, db_user, state, push=False)
        return
    if level == nav.NAV_SUPPORT:
        await open_support_home(message, session, db_user, state, push=False)
        return
    if level == nav.NAV_ADMIN:
        await open_admin_home(message, session, db_user, state, push=False)
        return
    if level == nav.NAV_ADMIN_PG:
        await open_pg_home(message, session, db_user, state, push=False)
        return
    if level == nav.NAV_ADMIN_USERS:
        await open_admin_users_hub(message, session, db_user, state, push=False)
        return
    if level == nav.NAV_ADMIN_RESELLERS:
        await open_admin_resellers_hub(message, session, db_user, state, push=False)
        return
    if level == nav.NAV_ADMIN_SETTINGS:
        await open_admin_settings_hub(message, session, db_user, state, push=False)
        return
    if level == nav.NAV_RESELLER:
        await open_reseller_home(
            message,
            session,
            db_user,
            state,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
            push=False,
        )
        return
    if level == nav.NAV_USER_PREVIEW:
        await nav.show_nav_keyboard(
            message,
            session,
            db_user,
            nav.NAV_USER_PREVIEW,
            text="👁 پیش‌نمایش منوی کاربر",
            state=state,
            push=False,
            as_user=True,
        )
        return
    if level == nav.NAV_PAY:
        data2 = await state.get_data()
        oid = data2.get(nav.PAY_ORDER_ID)
        if oid:
            await nav.show_nav_keyboard(
                message,
                session,
                db_user,
                nav.NAV_PAY,
                text="💳 روش پرداخت را انتخاب کنید:",
                state=state,
                push=False,
                order_id=int(oid),
            )
            return
        await open_wallet_home(message, session, db_user, state, push=False)
        return
    if level == nav.NAV_TOPUP_PAY:
        await open_wallet_home(message, session, db_user, state, push=False)
        return
    from app.bot.handlers.start import render_home

    await nav.clear_nav(state)
    await render_home(
        message,
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )


async def _handle_pay_action(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    action: str,
) -> None:
    from app.bot.handlers import shop as shop_h

    data = await state.get_data()
    order_id = data.get(nav.PAY_ORDER_ID)
    if not order_id:
        await message.answer("سفارش یافت نشد. دوباره از فروشگاه انتخاب کنید.")
        return
    order = await session.get(Order, int(order_id))
    if not order or int(order.user_id) != int(db_user.id):
        await restore_main_reply(
            message, session, db_user, text="دسترسی به این سفارش مجاز نیست.", state=state
        )
        return
    cb_map = {
        kb.REPLY_ACTION_PAY_WALLET: f"pay:wallet:{order.id}",
        kb.REPLY_ACTION_PAY_CARD: f"pay:card:{order.id}",
        kb.REPLY_ACTION_PAY_GATEWAY: f"pay:gateway:{order.id}",
        kb.REPLY_ACTION_PAY_CRYPTO: f"pay:crypto:{order.id}",
        kb.REPLY_ACTION_PAY_STARS: f"pay:stars:{order.id}",
        kb.REPLY_ACTION_PAY_DISCOUNT: f"pay:discount:{order.id}",
    }
    cb_data = cb_map.get(action)
    if not cb_data:
        return
    bubble = await message.answer("⏳")
    cb = _SoftCallback(bubble, cb_data)
    try:
        if action == kb.REPLY_ACTION_PAY_WALLET:
            await shop_h.pay_wallet_cb(cb, session, db_user)
        elif action == kb.REPLY_ACTION_PAY_CARD:
            await shop_h.pay_card_cb(cb, session, db_user)
        elif action == kb.REPLY_ACTION_PAY_GATEWAY:
            await shop_h.pay_gateway_cb(cb, session, db_user)
        elif action == kb.REPLY_ACTION_PAY_CRYPTO:
            await shop_h.pay_crypto_cb(cb, session, db_user)
        elif action == kb.REPLY_ACTION_PAY_STARS:
            await shop_h.pay_stars_cb(cb, session, db_user)
        elif action == kb.REPLY_ACTION_PAY_DISCOUNT:
            await shop_h.ask_discount(cb, state, session)
    except Exception as e:
        try:
            await bubble.edit_text(f"خطا: {e}")
        except Exception:
            await message.answer(f"خطا: {e}")


async def _handle_topup_action(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    action: str,
) -> None:
    from app.bot.handlers import wallet as wallet_h

    key = {
        kb.REPLY_ACTION_TOPUP_CARD: "wtop:card",
        kb.REPLY_ACTION_TOPUP_GATEWAY: "wtop:gateway",
        kb.REPLY_ACTION_TOPUP_CRYPTO: "wtop:crypto",
    }.get(action)
    if not key:
        return
    bubble = await message.answer("⏳")
    cb = _SoftCallback(bubble, key)
    try:
        await wallet_h.wtop_choose_method(cb, session, state, db_user)
    except Exception as e:
        try:
            await bubble.edit_text(f"خطا: {e}")
        except Exception:
            await message.answer(f"خطا: {e}")


async def _soft_reseller(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    action: str,
    *,
    is_reseller_bot: bool,
    reseller_owner_id: int | None,
) -> None:
    from app.bot.handlers import reseller as res_h

    mapping = {
        "res_dash": "res:dash",
        "res_users": "res:users:0",
        "res_stats": "res:stats",
        "res_plans": "res:plans",
        "res_orders": "res:orders",
        "res_payments": "res:payments",
        "res_tickets": "res:tickets",
        "res_settings": "res:st:hub",
    }
    data = mapping.get(action)
    if not data:
        return
    bubble = await message.answer("⏳")
    cb = _SoftCallback(bubble, data)
    # Call the matching reseller callback by name when available
    name_map = {
        "res:dash": "res_dash",
        "res:users:0": "res_users",
        "res:stats": "res_stats",
        "res:plans": "res_plans",
        "res:orders": "res_orders",
        "res:payments": "res_payments",
        "res:tickets": "res_tickets",
        "res:st:hub": "res_st_hub",
    }
    fn_name = name_map.get(data)
    fn = getattr(res_h, fn_name, None) if fn_name else None
    if fn is None:
        # Fallback: open reseller home inline
        from app.services.reseller_access import load_reseller_actor

        _oid, profile = await load_reseller_actor(
            session,
            db_user,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
        await bubble.edit_text(
            format_message("🤝 پنل نماینده", "بخش را از دکمه‌های زیر انتخاب کنید."),
            reply_markup=kb.reseller_home(profile),
        )
        return
    try:
        await fn(
            cb,
            session,
            db_user,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
    except TypeError:
        await fn(cb, session, db_user)


@router.message(F.text, ReplyMenuTextFilter())
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
    """Handle taps on the reply keyboard."""
    from app.bot.handlers.start import render_home

    action = reply_action
    ui = reply_ui
    role = reply_role

    preserve_state = action in {
        kb.REPLY_ACTION_BACK,
        kb.REPLY_ACTION_PAY_WALLET,
        kb.REPLY_ACTION_PAY_CARD,
        kb.REPLY_ACTION_PAY_GATEWAY,
        kb.REPLY_ACTION_PAY_CRYPTO,
        kb.REPLY_ACTION_PAY_STARS,
        kb.REPLY_ACTION_PAY_DISCOUNT,
        kb.REPLY_ACTION_TOPUP_CARD,
        kb.REPLY_ACTION_TOPUP_GATEWAY,
        kb.REPLY_ACTION_TOPUP_CRYPTO,
        kb.REPLY_ACTION_WALLET_TOPUP,
        kb.REPLY_ACTION_SUPPORT_NEW,
    }
    if not preserve_state:
        await state.clear()

    if action == kb.REPLY_ACTION_HOME:
        await nav.clear_nav(state)
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

    if action == kb.REPLY_ACTION_BACK:
        await handle_back(
            message,
            session,
            db_user,
            state,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
        return

    if action == kb.REPLY_ACTION_SHOP:
        await open_shop_list(message, session, db_user, state)
    elif action == kb.REPLY_ACTION_SERVICES:
        await open_services_list(message, session, db_user)
    elif action == kb.REPLY_ACTION_WALLET:
        await open_wallet_home(message, session, db_user, state)
    elif action == kb.REPLY_ACTION_WALLET_TOPUP:
        await open_wallet_topup(message, session, state)
    elif action == kb.REPLY_ACTION_WALLET_TX:
        await open_wallet_tx(message, session, db_user)
    elif action == kb.REPLY_ACTION_SUPPORT:
        await open_support_home(message, session, db_user, state)
    elif action == kb.REPLY_ACTION_SUPPORT_NEW:
        await open_support_new(message, session, state)
    elif action == kb.REPLY_ACTION_SUPPORT_LIST:
        await open_support_list(message, session, db_user)
    elif action == kb.REPLY_ACTION_REFERRAL:
        await open_referral(message, session, db_user)
    elif action == kb.REPLY_ACTION_RESELLER_APPLY:
        await open_reseller_apply(message, session, db_user)
    elif action == kb.REPLY_ACTION_RESELLER:
        await open_reseller_home(
            message,
            session,
            db_user,
            state,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
    elif action == kb.REPLY_ACTION_CREDS:
        await open_reseller_creds(message, session, db_user)
    elif action == kb.REPLY_ACTION_ADMIN:
        await open_admin_home(message, session, db_user, state)
    elif action == kb.REPLY_ACTION_ADMIN_PREVIEW:
        await open_user_preview(message, session, db_user, state)
    elif action == kb.REPLY_ACTION_ADMIN_DASH:
        await _soft_admin(message, session, db_user, "adm:dash", state)
    elif action == kb.REPLY_ACTION_ADMIN_ORDERS:
        await _soft_admin(message, session, db_user, "adm:orders", state)
    elif action == kb.REPLY_ACTION_ADMIN_PAYMENTS:
        await _soft_admin(message, session, db_user, "adm:payments", state)
    elif action == kb.REPLY_ACTION_ADMIN_TICKETS:
        await _soft_admin(message, session, db_user, "adm:tickets", state)
    elif action == kb.REPLY_ACTION_ADMIN_PLANS:
        await _soft_admin(message, session, db_user, "adm:plans", state)
    elif action == kb.REPLY_ACTION_ADMIN_PG:
        await open_pg_home(message, session, db_user, state)
    elif action == kb.REPLY_ACTION_ADMIN_USERS:
        await open_admin_users_hub(message, session, db_user, state)
    elif action == kb.REPLY_ACTION_ADMIN_SETTINGS:
        await open_admin_settings_hub(message, session, db_user, state)
    elif action == kb.REPLY_ACTION_ADMIN_BROADCAST:
        await _soft_admin(message, session, db_user, "adm:broadcast", state)
    elif action == kb.REPLY_ACTION_ADMIN_RESELLERS:
        await open_admin_resellers_hub(message, session, db_user, state)
    elif action == kb.REPLY_ACTION_ADMIN_BACKUP:
        await _soft_admin(message, session, db_user, "adm:backup", state)
    elif action == kb.REPLY_ACTION_PG_STATS:
        await _soft_admin(message, session, db_user, "adm:pg:stats", state)
    elif action == kb.REPLY_ACTION_PG_USERS:
        await _soft_admin(message, session, db_user, "adm:pg:users", state)
    elif action == kb.REPLY_ACTION_PG_CREATE:
        await _soft_admin(message, session, db_user, "adm:pg:create", state)
    elif action == kb.REPLY_ACTION_PG_SEARCH:
        await _soft_admin(message, session, db_user, "adm:pg:search", state)
    elif action == kb.REPLY_ACTION_PG_NODES:
        await _soft_admin(message, session, db_user, "adm:pg:nodes", state)
    elif action == kb.REPLY_ACTION_PG_GROUP:
        await _soft_admin(message, session, db_user, "adm:pg:group", state)
    elif action == kb.REPLY_ACTION_PG_TEMPLATE:
        await _soft_admin(message, session, db_user, "adm:pg:template", state)
    elif action == kb.REPLY_ACTION_ADM_USERS_LIST:
        await _soft_admin(message, session, db_user, "adm:users:list:0", state)
    elif action == kb.REPLY_ACTION_ADM_USERS_SEARCH:
        await _soft_admin(message, session, db_user, "adm:users:search", state)
    elif action == kb.REPLY_ACTION_ADM_USERS_WEB:
        await _soft_admin(message, session, db_user, "adm:users:webhint", state)
    elif action == kb.REPLY_ACTION_ADM_RES_LIST:
        await _soft_admin(message, session, db_user, "adm:resellers:list:0", state)
    elif action == kb.REPLY_ACTION_ADM_RES_APPS:
        await _soft_admin(message, session, db_user, "adm:resapp:list", state)
    elif action == kb.REPLY_ACTION_ADM_RES_ADD:
        await _soft_admin(message, session, db_user, "adm:resellers:add", state)
    elif action.startswith("adm_st_"):
        sec = action.replace("adm_st_", "", 1)
        await _soft_admin(message, session, db_user, f"adm:st:sec:{sec}", state)
    elif action.startswith("res_"):
        await _soft_reseller(
            message,
            session,
            db_user,
            action,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
    elif action.startswith("pay_"):
        await _handle_pay_action(message, session, db_user, state, action)
    elif action.startswith("topup_"):
        await _handle_topup_action(message, session, db_user, state, action)


@router.message(F.text.func(kb.is_cancel_text))
async def global_cancel_restore(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    """Fallback: انصراف always restores the main reply keyboard.

    Specific FSM handlers registered earlier may handle cancel first; this
    catches remaining cases so the main menu never stays stuck on cancel-only KB.
    """
    current = await state.get_state()
    if current is None:
        # Not in a flow — treat as home
        await restore_main_reply(
            message,
            session,
            db_user,
            text="🏠 منوی اصلی",
            state=state,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
        return
    # Let specific handlers run first when they match; if we got here, restore.
    await restore_main_reply(
        message,
        session,
        db_user,
        text="لغو شد.",
        state=state,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
