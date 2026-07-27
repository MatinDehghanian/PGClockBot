from __future__ import annotations

"""Receipt submission: manual admin approve or optional auto-approve."""

from typing import Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import get_settings
from app.db.models import BotUser, Payment, UserService
from app.services.formatting import format_message, format_toman, service_card
from app.services.orders import approve_payment
from app.services.pasarguard import get_pg
from app.services.users import get_all_settings, get_setting, on


async def build_approved_user_text(session: AsyncSession, payment: Payment, order) -> tuple[str, Any]:
    """Return (text, reply_markup) after a successful approval."""
    ui = await get_all_settings(session)
    markup = kb.back_home(ui)
    if order and order.service_id:
        svc = await session.get(UserService, order.service_id)
        try:
            text = ui["purchase_success_text"].format(order_id=order.id)
        except Exception:
            text = f"✅ سفارش #{order.id} فعال شد."
        if svc and svc.subscription_token:
            try:
                info = await get_pg().subscription_info(svc.subscription_token)
                text += "\n\n" + service_card(info)
            except Exception:
                pass
            if svc.subscription_url:
                text += f"\n\n🔗 لینک اشتراک:\n<code>{svc.subscription_url}</code>"
            markup = kb.service_actions(svc.id, ui)
        return format_message("✅ تحویل شد", text), markup
    if payment.is_wallet_topup:
        text = (
            f"✅ کیف پول شما "
            f"{format_toman(payment.amount, get_settings().currency)} شارژ شد."
        )
        return format_message("💰 شارژ کیف پول", text), markup
    return format_message("✅ تأیید شد", f"پرداخت #{payment.id} تأیید شد."), markup


async def notify_admins_receipt(bot: Bot, payment: Payment, user_tg_id: int | None) -> None:
    settings = get_settings()
    caption = format_message(
        "🧾 رسید جدید",
        f"پرداخت #{payment.id}\n"
        f"مبلغ: {format_toman(payment.amount, settings.currency)}\n"
        f"کاربر: {user_tg_id or '—'}\n"
        f"نوع: {'شارژ کیف' if payment.is_wallet_topup else 'خرید'}",
    )
    for admin_id in settings.admin_ids:
        try:
            if payment.receipt_file_id:
                await bot.send_photo(
                    admin_id,
                    photo=payment.receipt_file_id,
                    caption=caption,
                    reply_markup=kb.payment_review(payment.id),
                )
            else:
                await bot.send_message(
                    admin_id,
                    caption,
                    reply_markup=kb.payment_review(payment.id),
                )
        except Exception:
            try:
                await bot.send_message(
                    admin_id,
                    caption,
                    reply_markup=kb.payment_review(payment.id),
                )
            except Exception:
                pass


async def process_receipt(
    session: AsyncSession,
    payment: Payment,
    *,
    bot: Bot,
    user_tg_id: int | None,
) -> str:
    """
    After receipt is attached:
    - if auto_approve_payments=1 → approve & deliver, notify user text returned
    - else → notify admins for manual approve
    """
    auto = on(await get_setting(session, "auto_approve_payments", "0"))
    if auto:
        try:
            order = await approve_payment(session, payment, reviewer_tg=0)
            text, _ = await build_approved_user_text(session, payment, order)
            # also ping admins that it was auto-approved
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
            return text
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
