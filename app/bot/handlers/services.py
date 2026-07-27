from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import get_settings
from app.db.models import BotUser, UserService
from app.services.formatting import format_toman, service_card
from app.services.orders import get_plan, list_active_plans
from app.services.pasarguard import get_pg
from app.services.users import get_all_settings

router = Router(name="services")


@router.callback_query(F.data == "svc:list")
async def svc_list(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    ui = await get_all_settings(session)
    result = await session.execute(
        select(UserService)
        .where(UserService.bot_user_id == db_user.id)
        .order_by(UserService.id.desc())
    )
    services = list(result.scalars().all())
    if not services:
        if callback.message:
            await callback.message.edit_text(
                ui.get("empty_services_text")
                or "هنوز سرویسی ندارید.\nاز بخش «خرید سرویس» شروع کنید.",
                reply_markup=kb.main_menu(db_user.role, has_services=False, ui=ui),
            )
        return
    if callback.message:
        await callback.message.edit_text(
            "📦 <b>سرویس‌های شما</b>",
            reply_markup=kb.services_keyboard(services, ui),
        )


@router.callback_query(F.data.startswith("svc:view:"))
async def svc_view(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    ui = await get_all_settings(session)
    svc_id = int(callback.data.split(":")[-1])
    svc = await session.get(UserService, svc_id)
    if not svc or svc.bot_user_id != db_user.id:
        await callback.answer("یافت نشد", show_alert=True)
        return
    await callback.answer()
    from app.services.formatting import format_message

    text = format_message("📦 سرویس", f"🔹 <b>{svc.pg_username}</b>")
    if svc.subscription_token:
        try:
            info = await get_pg().subscription_info(svc.subscription_token)
            text = format_message("📦 سرویس شما", service_card(info))
        except Exception as e:
            text = format_message("📦 سرویس", f"🔹 <b>{svc.pg_username}</b>\n\nخطا در دریافت وضعیت: {e}")
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.service_actions(svc.id, ui))


@router.callback_query(F.data.startswith("svc:link:"))
async def svc_link(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    from app.services.delivery import send_subscription_qr_photo
    from app.services.formatting import format_message
    from app.services.users import on

    ui = await get_all_settings(session)
    svc_id = int(callback.data.split(":")[-1])
    svc = await session.get(UserService, svc_id)
    if not svc or svc.bot_user_id != db_user.id:
        await callback.answer("یافت نشد", show_alert=True)
        return
    await callback.answer()
    url = svc.subscription_url or ""
    sub_info = None
    if svc.subscription_token:
        try:
            sub_info = await get_pg().subscription_info(svc.subscription_token)
        except Exception:
            sub_info = None
    parts = ["🔗 لینک و QR اشتراک"]
    if url and on(ui.get("show_sub_link_in_text", "1")):
        parts.append(f"<code>{url}</code>")
    elif not url:
        parts.append("لینک موجود نیست.")
    if isinstance(sub_info, dict):
        from app.services.formatting import format_bytes, format_expire

        parts.append(
            f"📦 حجم: <b>{format_bytes(sub_info.get('used_traffic'))} از "
            f"{format_bytes(sub_info.get('data_limit'))}</b>"
        )
        parts.append(f"⏱ زمان: <b>{format_expire(sub_info.get('expire'))}</b>")
    text = format_message("📱 اشتراک", "\n\n".join(parts))
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=kb.service_actions(svc.id, ui))
        except Exception:
            await callback.message.answer(text, reply_markup=kb.service_actions(svc.id, ui))
    if url:
        await send_subscription_qr_photo(
            callback.bot,
            db_user.telegram_id,
            url,
            ui,
            info=sub_info if isinstance(sub_info, dict) else None,
            username=svc.pg_username,
        )


@router.callback_query(F.data.startswith("svc:renew:"))
async def svc_renew(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    ui = await get_all_settings(session)
    svc_id = int(callback.data.split(":")[-1])
    svc = await session.get(UserService, svc_id)
    if not svc or svc.bot_user_id != db_user.id:
        await callback.answer("یافت نشد", show_alert=True)
        return
    plans = await list_active_plans(session, include_trial=False)
    if not plans:
        await callback.answer("پلنی نیست", show_alert=True)
        return
    await callback.answer()
    rows = [
        [
            InlineKeyboardButton(
                text=f"{p.name} — {format_toman(p.price, get_settings().currency)}",
                callback_data=f"svc:renewpay:{svc_id}:{p.id}",
            )
        ]
        for p in plans
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=ui.get("btn_back", "⬅️ بازگشت"),
                callback_data=f"svc:view:{svc_id}",
            )
        ]
    )
    if callback.message:
        await callback.message.edit_text(
            "پلن تمدید را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("svc:renewpay:"))
async def svc_renew_pay(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    ui = await get_all_settings(session)
    _, _, svc_id, plan_id = callback.data.split(":")
    svc = await session.get(UserService, int(svc_id))
    plan = await get_plan(session, int(plan_id))
    if not svc or not plan or svc.bot_user_id != db_user.id:
        await callback.answer("نامعتبر", show_alert=True)
        return
    from app.services.orders import renew_service_with_plan

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

    await callback.answer()
    if pay_wallet:
        text = f"✅ تمدید با کیف پول انجام شد.\nسفارش #{order.id}"
        if callback.message:
            await callback.message.edit_text(
                text, reply_markup=kb.service_actions(svc.id, ui)
            )
        return

    amount = format_toman(order.amount, get_settings().currency)
    try:
        text = ui["card_pay_text"].format(
            amount=amount,
            card=ui.get("card_number") or "—",
            holder=ui.get("card_holder") or "—",
        )
    except Exception:
        text = f"💳 مبلغ تمدید: {amount}\nعکس رسید را ارسال کنید."
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.back_home(ui))
