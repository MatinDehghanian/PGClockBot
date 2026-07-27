from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.db.models import BotUser, Payment, Role
from app.services.delivery import send_delivery_to_user
from app.services.formatting import format_message
from app.services.orders import approve_payment, reject_payment
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
    await send_delivery_to_user(callback.bot, user.telegram_id, session, payment, order)
    try:
        from app.services.notifications import notify_new_subscription, notify_wallet_topup_ok

        if payment.is_wallet_topup:
            await notify_wallet_topup_ok(callback.bot, session, payment, user.telegram_id)
        elif order:
            from app.db.models import Plan

            plan = await session.get(Plan, order.plan_id) if order.plan_id else None
            await notify_new_subscription(
                callback.bot,
                session,
                order=order,
                user_tg_id=user.telegram_id,
                user_name=user.full_name or user.username,
                plan_name=plan.name if plan else None,
                needs_approval=False,
            )
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
        reject_body = ui.get("payment_reject_text") or (
            "پرداخت شما رد شد. اگر اشتباهی رخ داده با پشتیبانی در تماس باشید."
        )
        try:
            await callback.bot.send_message(
                user.telegram_id,
                format_message("❌ پرداخت رد شد", reject_body),
                reply_markup=kb.back_home(ui),
            )
        except Exception:
            pass
