from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import get_settings
from app.db.models import (
    BotUser,
    Order,
    Payment,
    PaymentStatus,
    Role,
    Ticket,
    TicketStatus,
)
from app.services.formatting import format_message, format_toman, order_status_fa
from app.services.reseller_access import load_reseller_actor
from app.services.resellers import (
    create_application,
    has_bot_perm,
    list_active_reseller_plans,
)
from app.bot.tg_utils import safe_edit_text
from app.services.users import get_all_settings

router = Router(name="reseller")


async def _actor(
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    return await load_reseller_actor(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )


@router.callback_query(F.data == "res:creds")
async def res_creds(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    """Credentials / deep-link card — available on the main bot for shop owners."""
    from app.services.resellers import format_reseller_access_card, get_reseller_profile

    if is_reseller_bot:
        # On shop bot, send them to the real panel
        owner_id, profile = await _actor(
            session,
            db_user,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
        if owner_id and profile:
            await callback.answer()
            if callback.message:
                await safe_edit_text(
                    callback.message,
                    format_message("🤝 پنل نماینده", "دسترسی‌ها با وب‌پنل یکسان است."),
                    reply_markup=kb.reseller_home(profile),
                )
            return
    if db_user.role != Role.RESELLER.value:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    profile = await get_reseller_profile(session, db_user.id)
    if not profile or not profile.is_active:
        await callback.answer("پروفایل نماینده یافت نشد", show_alert=True)
        return
    await callback.answer()
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
    if callback.message:
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data == "res:home")
async def res_home(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    # Full panel only on dedicated shop bot — main bot redirects to credentials
    if not is_reseller_bot:
        await res_creds(
            callback,
            session,
            db_user,
            is_reseller_bot=False,
            reseller_owner_id=None,
        )
        return
    owner_id, profile = await _actor(
        session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id
    )
    if not owner_id or not profile:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await safe_edit_text(
            callback.message,
            format_message("🤝 پنل نماینده", "دسترسی‌ها با وب‌پنل یکسان است."),
            reply_markup=kb.reseller_home(profile),
        )


@router.callback_query(F.data == "res:dash")
async def res_dash(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    owner_id, profile = await _actor(
        session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id
    )
    if not owner_id or not profile:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    if not has_bot_perm(profile, "dashboard"):
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    await callback.answer()
    users_n = await session.scalar(
        select(func.count()).select_from(BotUser).where(BotUser.reseller_id == owner_id)
    ) or 0
    orders_n = await session.scalar(
        select(func.count()).select_from(Order).where(Order.reseller_id == owner_id)
    ) or 0
    pending_pay = await session.scalar(
        select(func.count())
        .select_from(Payment)
        .join(BotUser, BotUser.id == Payment.user_id)
        .where(
            BotUser.reseller_id == owner_id,
            Payment.status == PaymentStatus.PENDING.value,
            Payment.receipt_file_id.is_not(None),
        )
    ) or 0
    open_tickets = await session.scalar(
        select(func.count())
        .select_from(Ticket)
        .join(BotUser, BotUser.id == Ticket.user_id)
        .where(
            BotUser.reseller_id == owner_id,
            Ticket.status == TicketStatus.OPEN.value,
        )
    ) or 0
    text = (
        "🏠 <b>خانه نماینده</b>\n\n"
        f"👥 مشتریان: {users_n}\n"
        f"🛒 سفارش‌ها: {orders_n}\n"
        f"🧾 رسید معلق: {pending_pay}\n"
        f"🎫 تیکت باز: {open_tickets}\n"
        f"💼 کمیسیون: {profile.commission_percent}٪"
    )
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=kb.reseller_home(profile))


RES_USERS_PAGE = 10


@router.callback_query(F.data.startswith("res:users:"))
async def res_users_list(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    owner_id, profile = await _actor(
        session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id
    )
    if not owner_id or not profile:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    if not has_bot_perm(profile, "dashboard"):
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    try:
        page = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        page = 0
    page = max(0, page)
    await callback.answer()
    total = await session.scalar(
        select(func.count()).select_from(BotUser).where(BotUser.reseller_id == owner_id)
    ) or 0
    result = await session.execute(
        select(BotUser)
        .where(BotUser.reseller_id == owner_id)
        .order_by(BotUser.id.desc())
        .offset(page * RES_USERS_PAGE)
        .limit(RES_USERS_PAGE)
    )
    users = list(result.scalars().all())
    buttons: list[InlineKeyboardButton] = []
    for u in users:
        name = (u.full_name or u.username or str(u.telegram_id))[:18]
        flag = "🚫" if u.is_blocked else "👤"
        buttons.append(
            InlineKeyboardButton(
                text=f"{flag} {name}",
                callback_data=f"res:user:{u.id}",
            )
        )
    rows: list[list[InlineKeyboardButton]] = kb.chunk_buttons(buttons, cols=2)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ قبل", callback_data=f"res:users:{page - 1}"))
    if (page + 1) * RES_USERS_PAGE < total:
        nav.append(InlineKeyboardButton(text="بعد ▶️", callback_data=f"res:users:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="res:home")])
    text = (
        f"👥 <b>مشتریان من</b>\n"
        f"صفحه {page + 1} از {max(1, (total + RES_USERS_PAGE - 1) // RES_USERS_PAGE)}"
        f" · {total} نفر"
    )
    if not users:
        text += "\n\nهنوز مشتری ثبت‌شده‌ای ندارید."
    if callback.message:
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("res:user:"))
async def res_user_view(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    owner_id, profile = await _actor(
        session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id
    )
    if not owner_id or not profile:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    try:
        uid = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("نامعتبر", show_alert=True)
        return
    user = await session.get(BotUser, uid)
    if not user or int(user.reseller_id or 0) != int(owner_id):
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    await callback.answer()
    blocked = "بله" if user.is_blocked else "خیر"
    display = html.escape(user.full_name or user.username or "—")
    uname = html.escape(user.username or "—")
    text = (
        f"👤 <b>{display}</b>\n\n"
        f"آیدی: <code>{user.telegram_id}</code>\n"
        f"یوزرنیم: @{uname}\n"
        f"کیف پول: {format_toman(user.wallet_balance, get_settings().currency)}\n"
        f"مسدود: {blocked}"
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ لیست مشتریان", callback_data="res:users:0")],
            [InlineKeyboardButton(text="🏠 خانه نماینده", callback_data="res:home")],
        ]
    )
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=markup)


@router.callback_query(F.data == "res:stats")
async def res_stats(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    owner_id, profile = await _actor(
        session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id
    )
    if not owner_id or not profile:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    if not has_bot_perm(profile, "stats"):
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    await callback.answer()
    text = (
        "📊 <b>آمار و کمیسیون</b>\n\n"
        f"کمیسیون: {profile.commission_percent}%\n"
        f"موجودی کمیسیون: {format_toman(profile.balance, get_settings().currency)}\n"
        f"تأیید رسید: {'بله' if has_bot_perm(profile, 'payments') else 'خیر'}\n"
        f"وب‌پنل: <code>{profile.web_username or '—'}</code>\n"
        f"ربات: <code>{('@' + profile.bot_username) if profile.bot_username else '—'}</code>\n"
        f"ادمین PG: <code>{profile.pg_admin_username or '—'}</code>"
    )
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=kb.reseller_home(profile))


@router.callback_query(F.data == "res:orders")
async def res_orders(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    owner_id, profile = await _actor(
        session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id
    )
    if not owner_id or not profile:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    if not has_bot_perm(profile, "orders"):
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    await callback.answer()
    result = await session.execute(
        select(Order)
        .where(Order.reseller_id == owner_id)
        .order_by(Order.id.desc())
        .limit(15)
    )
    orders = list(result.scalars().all())
    if not orders:
        if callback.message:
            await safe_edit_text(
                callback.message,
                "سفارشی برای مشتریان شما ثبت نشده.",
                reply_markup=kb.reseller_home(profile),
            )
        return
    lines = ["🛒 <b>آخرین سفارش‌های مشتریان</b>\n"]
    for o in orders:
        lines.append(
            f"#{o.id} — {format_toman(o.amount, get_settings().currency)} — "
            f"{order_status_fa(o.status)}"
        )
    if callback.message:
        await safe_edit_text(
            callback.message,
            "\n".join(lines),
            reply_markup=kb.reseller_home(profile),
        )


@router.callback_query(F.data == "res:tickets")
async def res_tickets(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    owner_id, profile = await _actor(
        session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id
    )
    if not owner_id or not profile:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    if not has_bot_perm(profile, "tickets"):
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    await callback.answer()
    result = await session.execute(
        select(Ticket, BotUser)
        .join(BotUser, BotUser.id == Ticket.user_id)
        .where(
            BotUser.reseller_id == owner_id,
            Ticket.status.in_([TicketStatus.OPEN.value, TicketStatus.ANSWERED.value]),
        )
        .order_by(Ticket.id.desc())
        .limit(15)
    )
    rows = result.all()
    if not rows:
        if callback.message:
            await safe_edit_text(
                callback.message,
                "تیکت بازی از مشتریان نیست.",
                reply_markup=kb.reseller_home(profile),
            )
        return
    lines = ["🎫 <b>تیکت‌های مشتریان</b>\n"]
    for t, u in rows:
        lines.append(f"#{t.id} — {t.subject[:40]} — {u.full_name or u.telegram_id}")
    lines.append("\nپاسخ کامل از وب‌پنل نماینده.")
    if callback.message:
        await safe_edit_text(
            callback.message,
            "\n".join(lines),
            reply_markup=kb.reseller_home(profile),
        )


@router.callback_query(F.data == "res:payments")
async def res_payments(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    owner_id, profile = await _actor(
        session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id
    )
    if not owner_id or not profile:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    if not has_bot_perm(profile, "payments"):
        await callback.answer("اجازه تأیید ندارید", show_alert=True)
        return
    await callback.answer()
    result = await session.execute(
        select(Payment, BotUser)
        .join(BotUser, BotUser.id == Payment.user_id)
        .where(
            BotUser.reseller_id == owner_id,
            Payment.status == PaymentStatus.PENDING.value,
            Payment.receipt_file_id.is_not(None),
        )
        .order_by(Payment.id.desc())
        .limit(20)
    )
    rows = result.all()
    if not rows:
        if callback.message:
            await safe_edit_text(callback.message, "رسید معلقی نیست.", reply_markup=kb.reseller_home(profile))
        return
    for payment, user in rows:
        caption = (
            f"رسید #{payment.id}\nکاربر: {user.full_name}\n"
            f"مبلغ: {format_toman(payment.amount, get_settings().currency)}"
        )
        try:
            if payment.receipt_file_id:
                await callback.bot.send_photo(
                    db_user.telegram_id,
                    photo=payment.receipt_file_id,
                    caption=caption,
                    reply_markup=kb.payment_review(payment.id),
                )
            else:
                await callback.bot.send_message(
                    db_user.telegram_id,
                    caption,
                    reply_markup=kb.payment_review(payment.id),
                )
        except Exception:
            pass
    if callback.message:
        await safe_edit_text(callback.message, "رسیدهای باز ارسال شد.", reply_markup=kb.reseller_home(profile))


@router.callback_query(F.data == "resapply:home")
async def resapply_home(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    ui = await get_all_settings(session)
    order_keys = [p.strip() for p in (ui.get("menu_order") or "").split(",") if p.strip()]
    if "reseller_apply" not in order_keys:
        await callback.answer("درخواست نمایندگی در منو فعال نیست", show_alert=True)
        return
    owner_id, _profile = await _actor(
        session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id
    )
    if owner_id or db_user.role == Role.RESELLER.value:
        await callback.answer("شما هم‌اکنون نماینده هستید", show_alert=True)
        return
    if db_user.role == Role.ADMIN.value:
        await callback.answer("ادمین نیاز به درخواست ندارد", show_alert=True)
        return
    plans = await list_active_reseller_plans(session)
    await callback.answer()
    if not plans:
        if callback.message:
            await safe_edit_text(callback.message, 
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
    rows.append([InlineKeyboardButton(text=ui.get("btn_back") or "بازگشت", callback_data="menu:home")])
    if callback.message:
        await safe_edit_text(callback.message, 
            format_message(
                "🤝 درخواست نمایندگی",
                "یکی از پلن‌های زیر را انتخاب کنید. پس از پرداخت (در صورت نیاز) ادمین درخواست را بررسی می‌کند.",
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("resapply:plan:"))
async def resapply_plan(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    owner_id, _profile = await _actor(
        session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id
    )
    if owner_id or db_user.role in (Role.RESELLER.value, Role.ADMIN.value):
        await callback.answer("اجازه درخواست نمایندگی ندارید", show_alert=True)
        return
    plan_id = int(callback.data.split(":")[-1])
    plans = {p.id: p for p in await list_active_reseller_plans(session)}
    plan = plans.get(plan_id)
    if not plan:
        await callback.answer("پلن یافت نشد", show_alert=True)
        return
    desc = html.escape(plan.description or "بدون توضیح")
    body = (
        f"{desc}\n\n"
        f"قیمت: <b>{format_toman(plan.price, get_settings().currency) if plan.price else 'رایگان'}</b>\n"
        f"کمیسیون: <b>{plan.commission_percent}٪</b>"
    )
    rows = [
        [InlineKeyboardButton(text="✅ ثبت درخواست", callback_data=f"resapply:buy:{plan.id}")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="resapply:home")],
    ]
    await callback.answer()
    if callback.message:
        await safe_edit_text(callback.message, 
            format_message(f"🤝 {plan.name}", body),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("resapply:buy:"))
async def resapply_buy(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    owner_id, _profile = await _actor(
        session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id
    )
    if owner_id or db_user.role in (Role.RESELLER.value, Role.ADMIN.value):
        await callback.answer("اجازه درخواست نمایندگی ندارید", show_alert=True)
        return
    ui = await get_all_settings(session)
    plan_id = int(callback.data.split(":")[-1])
    plans = {p.id: p for p in await list_active_reseller_plans(session)}
    plan = plans.get(plan_id)
    if not plan:
        await callback.answer("پلن یافت نشد", show_alert=True)
        return
    try:
        app, order = await create_application(session, user=db_user, plan=plan)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return

    await callback.answer()
    if order is None:
        if callback.message:
            await safe_edit_text(callback.message, 
                format_message(
                    "✅ درخواست ثبت شد",
                    f"درخواست #{app.id} برای پلن «{plan.name}» ثبت شد.\n"
                    "پس از تأیید ادمین، لینک راه‌اندازی وب‌پنل و ثبت ربات اختصاصی برایتان ارسال می‌شود.",
                ),
                reply_markup=kb.back_home(ui),
            )
        notify = (
            f"🤝 درخواست نمایندگی جدید #{app.id}\n"
            f"کاربر: {db_user.full_name or db_user.telegram_id}\n"
            f"پلن: {plan.name}"
        )
        for aid in get_settings().admin_ids:
            try:
                await callback.bot.send_message(
                    aid,
                    notify,
                    reply_markup=kb.reseller_app_review(app.id),
                )
            except Exception:
                pass
        return

    if not kb.any_checkout_method_enabled(ui):
        if callback.message:
            await safe_edit_text(callback.message, 
                format_message("⚠️ پرداخت غیرفعال", "روش پرداختی فعال نیست. با پشتیبانی تماس بگیرید."),
                reply_markup=kb.back_home(ui),
            )
        return

    text = format_message(
        f"🧾 سفارش نمایندگی #{order.id}",
        f"پلن: {plan.name}\nمبلغ: <b>{format_toman(order.amount, get_settings().currency)}</b>\n\n"
        "روش پرداخت را انتخاب کنید:",
    )
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=kb.pay_methods(order.id, ui))
