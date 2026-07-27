from __future__ import annotations

"""Receipt submission: manual admin approve or optional auto-approve."""

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import get_settings
from app.db.models import Payment
from app.services.delivery import send_delivery_to_user
from app.services.formatting import format_message, format_toman
from app.services.orders import approve_payment
from app.services.users import get_setting, on


async def notify_admins_receipt(bot: Bot, payment: Payment, user_tg_id: int | None) -> None:
    settings = get_settings()
    caption = format_message(
        "🧾 رسید جدید",
        f"پرداخت #{payment.id}\n"
        f"مبلغ: {format_toman(payment.amount, settings.currency)}\n"
        f"کاربر: {user_tg_id or '—'}\n"
        f"نوع: {'شارژ کیف' if payment.is_wallet_topup else 'خرید'}"
        + (f"\nسفارش: #{payment.order_id}" if payment.order_id else ""),
    )
    if payment.order_id and not payment.is_wallet_topup:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🟢✅ تأیید سفارش",
                        callback_data=f"ordrev:ok:{payment.order_id}",
                    ),
                    InlineKeyboardButton(
                        text="🔴❌ رد",
                        callback_data=f"ordrev:no:{payment.order_id}",
                    ),
                ],
                [InlineKeyboardButton(text="🛒 جزئیات سفارش", callback_data=f"adm:order:{payment.order_id}")],
            ]
        )
    else:
        markup = kb.payment_review(payment.id)
    for admin_id in settings.admin_ids:
        try:
            if payment.receipt_file_id:
                await bot.send_photo(
                    admin_id,
                    photo=payment.receipt_file_id,
                    caption=caption,
                    reply_markup=markup,
                )
            else:
                await bot.send_message(
                    admin_id,
                    caption,
                    reply_markup=markup,
                )
        except Exception:
            try:
                await bot.send_message(
                    admin_id,
                    caption,
                    reply_markup=markup,
                )
            except Exception:
                pass


async def process_receipt(
    session: AsyncSession,
    payment: Payment,
    *,
    bot: Bot,
    user_tg_id: int | None,
) -> str | None:
    """
    After receipt is attached:
    - if auto_approve_payments=1 → approve, deliver (+QR), return None (already sent)
    - else → notify admins; return status text for the user
    """
    auto = on(await get_setting(session, "auto_approve_payments", "0"))
    if auto:
        try:
            order = await approve_payment(session, payment, reviewer_tg=0)
            if user_tg_id:
                await send_delivery_to_user(bot, user_tg_id, session, payment, order)
            settings = get_settings()
            note = format_message(
                "⚡ تأیید خودکار",
                f"پرداخت #{payment.id} به‌صورت خودکار تأیید شد.",
            )
            for admin_id in settings.admin_ids:
                try:
                    await bot.send_message(admin_id, note)
                except Exception:
                    pass
            return None
        except Exception as e:
            await notify_admins_receipt(bot, payment, user_tg_id)
            return format_message(
                "⚠️ رسید ثبت شد",
                f"تأیید خودکار ناموفق بود ({e}).\nمنتظر تأیید دستی ادمین بمانید.",
            )

    await notify_admins_receipt(bot, payment, user_tg_id)
    return format_message(
        "✅ رسید دریافت شد",
        "رسید شما ثبت شد.\nپس از تأیید ادمین، سرویس/شارژ فعال می‌شود.",
    )
