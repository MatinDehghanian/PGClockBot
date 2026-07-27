from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.db.models import BotUser, Payment, Role
from app.services.formatting import format_message
from app.services.orders import approve_payment, reject_payment
from app.services.receipts import build_approved_user_text
from app.services.users import get_all_settings

router = Router(name="payments")


def _can_review(user: BotUser) -> bool:
    return user.role in {Role.ADMIN.value, Role.RESELLER.value}


@router.callback_query(F.data.startswith("payrev:ok:"))
async def pay_approve(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _can_review(db_user):
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    payment_id = int(callback.data.split(":")[-1])
    payment = await session.get(Payment, payment_id)
    if not payment:
        await callback.answer("یافت نشد", show_alert=True)
        return
    try:
        order = await approve_payment(session, payment, db_user.telegram_id)
    except Exception as e:
        await callback.answer(f"خطا: {e}", show_alert=True)
        return
    await callback.answer("تأیید شد ✅")
    if callback.message:
        try:
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=(callback.message.caption or "") + "\n\n✅ تأیید دستی شد"
                )
            else:
                await callback.message.edit_text(
                    (callback.message.text or "") + "\n\n✅ تأیید دستی شد"
                )
        except Exception:
            pass

    user = await session.get(BotUser, payment.user_id)
    if not user:
        return
    text, markup = await build_approved_user_text(session, payment, order)
    try:
        await callback.bot.send_message(user.telegram_id, text, reply_markup=markup)
    except Exception:
        pass


@router.callback_query(F.data.startswith("payrev:no:"))
async def pay_reject(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _can_review(db_user):
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    payment_id = int(callback.data.split(":")[-1])
    payment = await session.get(Payment, payment_id)
    if not payment:
        await callback.answer("یافت نشد", show_alert=True)
        return
    await reject_payment(session, payment, db_user.telegram_id, "rejected")
    await callback.answer("رد شد")
    if callback.message:
        try:
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=(callback.message.caption or "") + "\n\n❌ رد شد"
                )
            else:
                await callback.message.edit_text(
                    (callback.message.text or "") + "\n\n❌ رد شد"
                )
        except Exception:
            pass
    user = await session.get(BotUser, payment.user_id)
    ui = await get_all_settings(session)
    if user:
        try:
            await callback.bot.send_message(
                user.telegram_id,
                format_message("❌ پرداخت رد شد", f"پرداخت #{payment.id} توسط ادمین رد شد."),
                reply_markup=kb.back_home(ui),
            )
        except Exception:
            pass
