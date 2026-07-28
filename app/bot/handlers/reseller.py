from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import get_settings
from app.db.models import BotUser, Role
from app.services.formatting import format_message, format_toman
from app.services.resellers import (
    create_application,
    get_reseller_profile,
    has_bot_perm,
    list_active_reseller_plans,
)
from app.services.users import get_all_settings, on

router = Router(name="reseller")


@router.callback_query(F.data == "res:home")
async def res_home(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if db_user.role != Role.RESELLER.value:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    profile = await get_reseller_profile(session, db_user.id)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "🤝 <b>پنل نماینده</b>",
            reply_markup=kb.reseller_home(profile),
        )


@router.callback_query(F.data == "res:stats")
async def res_stats(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if db_user.role != Role.RESELLER.value:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    profile = await get_reseller_profile(session, db_user.id)
    if not profile or not has_bot_perm(profile, "stats"):
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    await callback.answer()
    text = (
        "📊 <b>وضعیت نماینده</b>\n\n"
        f"کمیسیون: {profile.commission_percent}%\n"
        f"موجودی کمیسیون: {format_toman(profile.balance, get_settings().currency)}\n"
        f"تأیید رسید: {'بله' if profile.can_approve_receipts else 'خیر'}\n"
        f"وب‌پنل: <code>{profile.web_username or '—'}</code>\n"
        f"ادمین PG: <code>{profile.pg_admin_username or '—'}</code>"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.reseller_home(profile))


@router.callback_query(F.data == "res:payments")
async def res_payments(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    from sqlalchemy import select

    from app.db.models import Payment, PaymentStatus

    if db_user.role != Role.RESELLER.value:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    profile = await get_reseller_profile(session, db_user.id)
    if not profile or not has_bot_perm(profile, "approve_receipts"):
        await callback.answer("اجازه تأیید ندارید", show_alert=True)
        return
    await callback.answer()
    result = await session.execute(
        select(Payment, BotUser)
        .join(BotUser, BotUser.id == Payment.user_id)
        .where(
            BotUser.reseller_id == db_user.id,
            Payment.status == PaymentStatus.PENDING.value,
            Payment.receipt_file_id.is_not(None),
        )
        .order_by(Payment.id.desc())
        .limit(20)
    )
    rows = result.all()
    if not rows:
        if callback.message:
            await callback.message.edit_text("رسید معلقی نیست.", reply_markup=kb.reseller_home(profile))
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
        await callback.message.edit_text("رسیدهای باز ارسال شد.", reply_markup=kb.reseller_home(profile))


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
            await callback.message.edit_text(
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
        await callback.message.edit_text(
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
        await callback.message.edit_text(
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
        # Free plan — waiting for admin
        if callback.message:
            await callback.message.edit_text(
                format_message(
                    "✅ درخواست ثبت شد",
                    f"درخواست #{app.id} برای پلن «{plan.name}» ثبت شد.\nپس از تأیید ادمین، اطلاعات ورود برایتان ارسال می‌شود.",
                ),
                reply_markup=kb.back_home(ui),
            )
        for aid in get_settings().admin_ids:
            try:
                await callback.bot.send_message(
                    aid,
                    f"🤝 درخواست نمایندگی جدید #{app.id}\n"
                    f"کاربر: {db_user.full_name or db_user.telegram_id}\n"
                    f"پلن: {plan.name}",
                )
            except Exception:
                pass
        return

    if not kb.any_checkout_method_enabled(ui):
        if callback.message:
            await callback.message.edit_text(
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
        await callback.message.edit_text(text, reply_markup=kb.pay_methods(order.id, ui))
