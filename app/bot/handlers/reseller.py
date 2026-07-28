from __future__ import annotations

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
from app.services.users import get_all_settings, on

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


@router.callback_query(F.data == "res:home")
async def res_home(
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
async def resapply_home(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    ui = await get_all_settings(session)
    if not on(ui.get("show_reseller_apply", "1")):
        await callback.answer("درخواست نمایندگی غیرفعال است", show_alert=True)
        return
    if db_user.role == Role.RESELLER.value:
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
async def resapply_plan(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    ui = await get_all_settings(session)
    plan_id = int(callback.data.split(":")[-1])
    plans = {p.id: p for p in await list_active_reseller_plans(session)}
    plan = plans.get(plan_id)
    if not plan:
        await callback.answer("پلن یافت نشد", show_alert=True)
        return
    desc = plan.description or "بدون توضیح"
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
async def resapply_buy(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
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
                    reply_markup=_notify_admins_markup(app.id),
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
