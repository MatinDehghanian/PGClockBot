from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.tg_utils import safe_edit_text
from app.config import get_settings
from app.db.models import BotUser, UserService
from app.services.formatting import format_message, format_toman, service_card
from app.services.orders import get_plan, list_active_plans
from app.services.pasarguard import get_pg
from app.services.users import get_all_settings

router = Router(name="services")


@router.callback_query(F.data == "svc:list")
async def svc_list(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
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
            await safe_edit_text(
                callback.message,
                ui.get("empty_services_text")
                or "هنوز سرویسی ندارید.\nاز بخش «خرید سرویس» شروع کنید.",
                reply_markup=kb.back_home(ui),
            )
        return
    if callback.message:
        await safe_edit_text(callback.message, 
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
    text = format_message("📦 سرویس", f"🔹 <b>{svc.pg_username}</b>")
    if svc.subscription_token:
        try:
            info = await get_pg().subscription_info(svc.subscription_token)
            text = format_message("📦 سرویس شما", service_card(info))
        except Exception as e:
            text = format_message("📦 سرویس", f"🔹 <b>{svc.pg_username}</b>\n\nخطا در دریافت وضعیت: {e}")
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=kb.service_actions(svc.id, ui))


@router.callback_query(F.data.startswith("svc:link:"))
async def svc_link(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    from app.services.delivery import send_subscription_qr_photo
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
            await safe_edit_text(callback.message, text, reply_markup=kb.service_actions(svc.id, ui))
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
        await safe_edit_text(callback.message, 
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
    if plan.price > 0 and not kb.any_checkout_method_enabled(ui):
        await callback.answer("هیچ روش پرداختی فعال نیست", show_alert=True)
        return

    from app.services.orders import renew_service_with_plan

    try:
        order = await renew_service_with_plan(
            session,
            user_id=db_user.id,
            service=svc,
            plan=plan,
        )
    except Exception as e:
        await callback.answer(str(e), show_alert=True)
        return

    await callback.answer()

    if order.amount <= 0:
        from app.services.orders import apply_renewal, mark_order_free_paid

        await mark_order_free_paid(session, order, db_user.id)
        try:
            order = await apply_renewal(session, order, svc, plan)
        except Exception as e:
            if callback.message:
                await safe_edit_text(callback.message, f"❌ {e}", reply_markup=kb.service_actions(svc.id, ui))
            return
        if callback.message:
            await safe_edit_text(callback.message, 
                format_message("✅ تمدید رایگان", f"سفارش #{order.id}"),
                reply_markup=kb.service_actions(svc.id, ui),
            )
        return

    text = format_message(
        f"🔄 تمدید — سفارش #{order.id}",
        f"مبلغ: <b>{format_toman(order.amount, get_settings().currency)}</b>\nروش پرداخت را انتخاب کنید:",
    )
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=kb.pay_methods(order.id, ui))
