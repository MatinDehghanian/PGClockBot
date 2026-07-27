from __future__ import annotations

"""Receipt submission: manual admin approve or optional auto-approve."""

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment
from app.services.delivery import send_delivery_to_user
from app.services.formatting import format_message
from app.services.notifications import (
    notify_auto_approve,
    notify_new_subscription,
    notify_pending_approval,
    notify_wallet_topup_ok,
)
from app.services.orders import approve_payment
from app.services.users import get_setting, on


async def notify_admins_receipt(
    bot: Bot,
    payment: Payment,
    user_tg_id: int | None,
    session: AsyncSession | None = None,
) -> None:
    """Notify admins of a receipt awaiting approval (respects prefs)."""
    if session is not None:
        await notify_pending_approval(bot, session, payment, user_tg_id)
        return
    from app.db.session import SessionLocal

    async with SessionLocal() as s:
        await notify_pending_approval(bot, s, payment, user_tg_id)


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
            await notify_auto_approve(bot, session, payment)
            if payment.is_wallet_topup:
                await notify_wallet_topup_ok(bot, session, payment, user_tg_id)
            elif order:
                plan_name = None
                if order.plan_id:
                    from app.db.models import Plan

                    plan = await session.get(Plan, order.plan_id)
                    plan_name = plan.name if plan else None
                await notify_new_subscription(
                    bot,
                    session,
                    order=order,
                    user_tg_id=user_tg_id,
                    plan_name=plan_name,
                    needs_approval=False,
                )
            return None
        except Exception as e:
            await notify_pending_approval(bot, session, payment, user_tg_id)
            return format_message(
                "⚠️ رسید ثبت شد",
                f"تأیید خودکار ناموفق بود ({e}).\nمنتظر تأیید دستی ادمین بمانید.",
            )

    await notify_pending_approval(bot, session, payment, user_tg_id)
    return format_message(
        "✅ رسید دریافت شد",
        "رسید شما ثبت شد.\nپس از تأیید ادمین، سرویس/شارژ فعال می‌شود.",
    )
