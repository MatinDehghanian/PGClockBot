from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.db.models import BotUser, Payment, PaymentStatus, Role
from app.services.formatting import format_toman
from app.services.resellers import get_reseller_profile
from app.config import get_settings

router = Router(name="reseller")


@router.callback_query(F.data == "res:home")
async def res_home(callback: CallbackQuery, db_user: BotUser):
    if db_user.role != Role.RESELLER.value:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("🤝 <b>پنل نماینده</b>", reply_markup=kb.reseller_home())


@router.callback_query(F.data == "res:stats")
async def res_stats(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if db_user.role != Role.RESELLER.value:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    await callback.answer()
    profile = await get_reseller_profile(session, db_user.id)
    if not profile:
        await callback.answer("پروفایل نیست", show_alert=True)
        return
    text = (
        "📊 <b>وضعیت نماینده</b>\n\n"
        f"کمیسیون: {profile.commission_percent}%\n"
        f"موجودی کمیسیون: {format_toman(profile.balance, get_settings().currency)}\n"
        f"تأیید رسید: {'بله' if profile.can_approve_receipts else 'خیر'}"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.reseller_home())


@router.callback_query(F.data == "res:payments")
async def res_payments(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if db_user.role != Role.RESELLER.value:
        await callback.answer("فقط نمایندگان", show_alert=True)
        return
    profile = await get_reseller_profile(session, db_user.id)
    if not profile or not profile.can_approve_receipts:
        await callback.answer("اجازه تأیید ندارید", show_alert=True)
        return
    await callback.answer()
    # pending payments of customers under this reseller
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
            await callback.message.edit_text("رسید معلقی نیست.", reply_markup=kb.reseller_home())
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
        await callback.message.edit_text("رسیدهای باز ارسال شد.", reply_markup=kb.reseller_home())
