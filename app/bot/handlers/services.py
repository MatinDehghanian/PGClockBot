from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.db.models import BotUser, UserService
from app.services.formatting import service_card
from app.services.orders import get_plan, list_active_plans
from app.services.pasarguard import get_pg
from app.services.formatting import format_toman
from app.config import get_settings

router = Router(name="services")


@router.callback_query(F.data == "svc:list")
async def svc_list(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    result = await session.execute(
        select(UserService)
        .where(UserService.bot_user_id == db_user.id)
        .order_by(UserService.id.desc())
    )
    services = list(result.scalars().all())
    if not services:
        if callback.message:
            await callback.message.edit_text(
                "سرویسی ندارید. از بخش خرید شروع کنید.",
                reply_markup=kb.main_menu(db_user.role, has_services=False),
            )
        return
    if callback.message:
        await callback.message.edit_text(
            "📦 <b>سرویس‌های شما</b>",
            reply_markup=kb.services_keyboard(services),
        )


@router.callback_query(F.data.startswith("svc:view:"))
async def svc_view(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    svc_id = int(callback.data.split(":")[-1])
    svc = await session.get(UserService, svc_id)
    if not svc or svc.bot_user_id != db_user.id:
        await callback.answer("یافت نشد", show_alert=True)
        return
    text = f"🔹 <b>{svc.pg_username}</b>"
    if svc.subscription_token:
        try:
            info = await get_pg().subscription_info(svc.subscription_token)
            text = service_card(info)
        except Exception as e:
            text += f"\nخطا در دریافت وضعیت: {e}"
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.service_actions(svc.id))


@router.callback_query(F.data.startswith("svc:link:"))
async def svc_link(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    svc_id = int(callback.data.split(":")[-1])
    svc = await session.get(UserService, svc_id)
    if not svc or svc.bot_user_id != db_user.id:
        await callback.answer("یافت نشد", show_alert=True)
        return
    text = f"🔗 لینک سابسکریپشن:\n<code>{svc.subscription_url or '—'}</code>"
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.service_actions(svc.id))


@router.callback_query(F.data.startswith("svc:renew:"))
async def svc_renew(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    svc_id = int(callback.data.split(":")[-1])
    svc = await session.get(UserService, svc_id)
    if not svc or svc.bot_user_id != db_user.id:
        await callback.answer("یافت نشد", show_alert=True)
        return
    plans = await list_active_plans(session, include_trial=False)
    if not plans:
        await callback.answer("پلنی نیست", show_alert=True)
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [
            InlineKeyboardButton(
                text=f"{p.name} — {format_toman(p.price, get_settings().currency)}",
                callback_data=f"svc:renewpay:{svc_id}:{p.id}",
            )
        ]
        for p in plans
    ]
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"svc:view:{svc_id}")])
    if callback.message:
        await callback.message.edit_text(
            "پلن تمدید را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("svc:renewpay:"))
async def svc_renew_pay(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    _, _, svc_id, plan_id = callback.data.split(":")
    svc = await session.get(UserService, int(svc_id))
    plan = await get_plan(session, int(plan_id))
    if not svc or not plan or svc.bot_user_id != db_user.id:
        await callback.answer("نامعتبر", show_alert=True)
        return
    from app.services.orders import renew_service_with_plan

    # Prefer wallet if enough balance else card flow
    pay_wallet = db_user.wallet_balance >= plan.price
    try:
        order = await renew_service_with_plan(
            session,
            user_id=db_user.id,
            service=svc,
            plan=plan,
            pay_wallet=pay_wallet,
            user=db_user,
        )
    except Exception as e:
        await callback.answer(str(e), show_alert=True)
        return

    if pay_wallet:
        text = f"✅ تمدید با کیف پول انجام شد.\nسفارش #{order.id}"
        if callback.message:
            await callback.message.edit_text(text, reply_markup=kb.service_actions(svc.id))
        return

    from app.services.users import get_setting

    card = await get_setting(session, "card_number")
    holder = await get_setting(session, "card_holder")
    text = (
        f"💳 مبلغ تمدید: {format_toman(order.amount, get_settings().currency)}\n"
        f"کارت: <code>{card or '—'}</code>\n{holder or ''}\n\nعکس رسید را ارسال کنید."
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.back_home())
