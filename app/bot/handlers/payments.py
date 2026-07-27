from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.db.models import BotUser, Order, Payment, Role, UserService
from app.services.formatting import format_toman, service_card
from app.services.orders import approve_payment, reject_payment
from app.services.pasarguard import get_pg
from app.config import get_settings

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
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n✅ تأیید شد"
        ) if callback.message.photo else await callback.message.edit_text(
            (callback.message.text or "") + "\n\n✅ تأیید شد"
        )

    # notify user
    user = await session.get(BotUser, payment.user_id)
    if not user:
        return
    text = f"✅ پرداخت #{payment.id} تأیید شد."
    markup = kb.back_home()
    if order and order.service_id:
        svc = await session.get(UserService, order.service_id)
        if svc and svc.subscription_token:
            try:
                info = await get_pg().subscription_info(svc.subscription_token)
                text += "\n\n" + service_card(info)
            except Exception:
                pass
            text += f"\n\n🔗 <code>{svc.subscription_url}</code>"
            markup = kb.service_actions(svc.id)
        elif payment.is_wallet_topup:
            text = f"✅ کیف پول شما {format_toman(payment.amount, get_settings().currency)} شارژ شد."
    elif payment.is_wallet_topup:
        text = f"✅ کیف پول شما {format_toman(payment.amount, get_settings().currency)} شارژ شد."
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
                await callback.message.edit_caption(caption=(callback.message.caption or "") + "\n\n❌ رد شد")
            else:
                await callback.message.edit_text((callback.message.text or "") + "\n\n❌ رد شد")
        except Exception:
            pass
    user = await session.get(BotUser, payment.user_id)
    if user:
        try:
            await callback.bot.send_message(user.telegram_id, f"❌ پرداخت #{payment.id} رد شد.")
        except Exception:
            pass
