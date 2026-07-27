from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import get_settings
from app.db.models import BotUser, Order, UserService
from app.services.delivery import send_delivery_to_user
from app.services.formatting import format_message, format_toman
from app.services.orders import create_order, get_plan, list_active_plans, pay_with_wallet, start_card_payment
from app.services.users import get_all_settings, get_setting, on

router = Router(name="shop")


class ShopStates(StatesGroup):
    discount = State()


@router.callback_query(F.data == "shop:list")
async def shop_list(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    ui = await get_all_settings(session)
    trial_on = on(ui.get("trial_enabled"))
    plans = await list_active_plans(session, include_trial=True)
    if not trial_on:
        plans = [p for p in plans if not p.is_trial]
    has_svc = (
        await session.execute(
            select(UserService.id).where(UserService.bot_user_id == db_user.id).limit(1)
        )
    ).scalar_one_or_none()
    if has_svc:
        plans = [p for p in plans if not p.is_trial]
    if not plans:
        text = format_message(
            "🛒 فروشگاه",
            ui.get("shop_empty_text")
            or "در حال حاضر پلنی برای فروش فعال نیست.",
        )
        if callback.message:
            await callback.message.edit_text(text, reply_markup=kb.back_home(ui))
        return
    if callback.message:
        await callback.message.edit_text(
            format_message("🛒 انتخاب پلن", "یکی از پلن‌ها را انتخاب کنید:"),
            reply_markup=kb.plans_keyboard(plans, ui),
        )


@router.callback_query(F.data.startswith("shop:plan:"))
async def shop_plan(callback: CallbackQuery, session: AsyncSession):
    ui = await get_all_settings(session)
    plan_id = int(callback.data.split(":")[-1])
    plan = await get_plan(session, plan_id)
    if not plan:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return
    await callback.answer()
    limit = f"{plan.data_limit_gb:g} گیگ" if plan.data_limit_gb is not None else "نامحدود"
    body = (
        f"{plan.description or ''}\n"
        f"⏱ مدت: {plan.duration_days} روز\n"
        f"📦 حجم: {limit}\n"
        f"💰 قیمت: {format_toman(plan.price, get_settings().currency)}"
    ).strip()
    text = format_message(f"💎 {plan.name}", body)
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.plan_actions(plan.id, ui))


@router.callback_query(F.data.startswith("shop:buy:"))
async def shop_buy(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    ui = await get_all_settings(session)
    plan_id = int(callback.data.split(":")[-1])
    order = await create_order(
        session,
        user_id=db_user.id,
        plan_id=plan_id,
        reseller_id=db_user.reseller_id,
    )
    text = format_message(
        f"🧾 سفارش #{order.id}",
        f"مبلغ قابل پرداخت:\n<b>{format_toman(order.amount, get_settings().currency)}</b>\n\n"
        "روش پرداخت را انتخاب کنید:",
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.pay_methods(order.id, ui))


@router.callback_query(F.data.startswith("pay:discount:"))
async def ask_discount(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    order_id = int(callback.data.split(":")[-1])
    await state.set_state(ShopStates.discount)
    await state.update_data(order_id=order_id)
    if callback.message:
        await callback.message.answer(
            "کد تخفیف را ارسال کنید یا «انصراف» بزنید:",
            reply_markup=kb.cancel_reply(),
        )


@router.message(ShopStates.discount)
async def apply_discount_msg(
    message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser
):
    ui = await get_all_settings(session)
    if (message.text or "").strip() == "انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.back_home(ui))
        return
    data = await state.get_data()
    order = await session.get(Order, data.get("order_id"))
    await state.clear()
    if not order or order.user_id != db_user.id:
        await message.answer("سفارش معتبر نیست.")
        return
    from app.services.orders import apply_discount

    discount, code = await apply_discount(
        session, message.text.strip(), order.amount + order.discount_amount
    )
    if not code:
        await message.answer("کد تخفیف نامعتبر است.", reply_markup=kb.pay_methods(order.id, ui))
        return
    base = order.amount + order.discount_amount
    order.discount_amount = discount
    order.discount_code = code
    order.amount = max(0, base - discount)
    await session.commit()
    await message.answer(
        f"تخفیف اعمال شد ✅\nمبلغ جدید: {format_toman(order.amount, get_settings().currency)}",
        reply_markup=kb.pay_methods(order.id, ui),
    )


@router.callback_query(F.data.startswith("pay:wallet:"))
async def pay_wallet_cb(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    ui = await get_all_settings(session)
    order_id = int(callback.data.split(":")[-1])
    order = await session.get(Order, order_id)
    if not order or order.user_id != db_user.id:
        await callback.answer("سفارش نامعتبر", show_alert=True)
        return
    try:
        order = await pay_with_wallet(session, order, db_user)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    except Exception as e:
        await callback.answer(f"خطا در تحویل: {e}", show_alert=True)
        return

    await callback.answer()
    if callback.message:
        try:
            await callback.message.edit_text(
                format_message("✅ خرید موفق", "سرویس در حال تحویل است…"),
                reply_markup=kb.back_home(ui),
            )
        except Exception:
            pass
    await send_delivery_to_user(
        callback.bot, db_user.telegram_id, session, None, order
    )


@router.callback_query(F.data.startswith("pay:card:"))
async def pay_card_cb(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    ui = await get_all_settings(session)
    order_id = int(callback.data.split(":")[-1])
    order = await session.get(Order, order_id)
    if not order or order.user_id != db_user.id:
        await callback.answer("سفارش نامعتبر", show_alert=True)
        return
    await callback.answer()
    payment = await start_card_payment(session, order, db_user.id)
    amount = format_toman(order.amount, get_settings().currency)
    try:
        body = ui["card_pay_text"].format(
            amount=amount,
            card=ui.get("card_number") or "—",
            holder=ui.get("card_holder") or "—",
        )
    except Exception:
        body = f"مبلغ {amount} را کارت به کارت کنید و رسید بفرستید."
    body += f"\n\n(پرداخت #{payment.id})"
    if callback.message:
        await callback.message.edit_text(
            format_message("💳 کارت به کارت", body),
            reply_markup=kb.back_home(ui),
        )
