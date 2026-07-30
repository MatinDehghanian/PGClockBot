from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.tg_utils import safe_edit_text
from app.config import get_settings
from app.db.models import BotUser, Order, PaymentMethod, UserService
from app.services.delivery import send_delivery_to_user
from app.services.formatting import format_message, format_toman
from app.services.orders import (
    calc_custom_plan_price,
    create_custom_order,
    create_order,
    get_plan,
    list_active_plans,
    mark_order_free_paid,
    pay_with_wallet,
    stars_amount_for_toman,
    start_card_payment,
    start_method_payment,
)
from app.services.users import get_all_settings, on

router = Router(name="shop")


class ShopStates(StatesGroup):
    discount = State()
    custom_gb_input = State()
    custom_days_input = State()


def _custom_bounds(ui: dict) -> tuple[int, int, int, int, int, int]:
    min_gb = max(1, int(float(ui.get("custom_plan_min_gb") or 1)))
    max_gb = max(min_gb, int(float(ui.get("custom_plan_max_gb") or 500)))
    min_days = max(1, int(float(ui.get("custom_plan_min_days") or 1)))
    max_days = max(min_days, int(float(ui.get("custom_plan_max_days") or 365)))
    price_gb = int(float(ui.get("custom_plan_price_per_gb") or 1000))
    price_day = int(float(ui.get("custom_plan_price_per_day") or 500))
    return min_gb, max_gb, min_days, max_days, price_gb, price_day


def _custom_has_pg_link(ui: dict) -> bool:
    tpl = (ui.get("custom_plan_template_id") or "").strip()
    groups = (ui.get("custom_plan_group_ids") or "").strip()
    return bool(tpl or groups)


async def _custom_available_for_users(
    session: AsyncSession,
    ui: dict,
    *,
    plans: list | None = None,
) -> bool:
    """Custom plan only when enabled, linked, AND at least one catalog plan exists."""
    if not on(ui.get("custom_plan_enabled")):
        return False
    from app.services.users import current_shop_reseller_id

    shop_rid = current_shop_reseller_id()
    if shop_rid is not None:
        # Mirror create_custom_order: reseller shops need their own PG link, not platform inheritance
        from app.db.models import ResellerSetting

        own = await session.execute(
            select(ResellerSetting).where(
                ResellerSetting.reseller_user_id == int(shop_rid),
                ResellerSetting.key.in_(
                    ("custom_plan_template_id", "custom_plan_group_ids")
                ),
            )
        )
        own_map = {r.key: (r.value or "").strip() for r in own.scalars().all()}
        if not (own_map.get("custom_plan_template_id") or own_map.get("custom_plan_group_ids")):
            return False
    elif not _custom_has_pg_link(ui):
        return False
    if plans is None:
        plans = await list_active_plans(session, include_trial=True)
    catalog = [p for p in plans if not p.is_trial]
    return bool(catalog)


@router.callback_query(F.data == "shop:list")
async def shop_list(callback: CallbackQuery, session: AsyncSession, db_user: BotUser, state: FSMContext):
    await callback.answer()
    await state.clear()
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
    # Custom plan only when catalog plans exist (and setting/link OK)
    custom_on = await _custom_available_for_users(session, ui, plans=plans)
    if not plans and not custom_on:
        text = format_message(
            "🛒 فروشگاه",
            ui.get("shop_empty_text")
            or "در حال حاضر پلنی برای فروش فعال نیست.",
        )
        if callback.message:
            await safe_edit_text(callback.message, text, reply_markup=kb.back_home(ui))
        return
    if callback.message:
        await safe_edit_text(callback.message, 
            format_message("🛒 انتخاب پلن", "یکی از پلن‌ها را انتخاب کنید:"),
            reply_markup=kb.plans_keyboard(plans, ui, custom_enabled=custom_on),
        )


@router.callback_query(F.data == "shop:custom:noop")
async def custom_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "shop:custom")
async def custom_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    ui = await get_all_settings(session)
    if not await _custom_available_for_users(session, ui):
        await callback.answer(
            "پلن دلخواه در دسترس نیست (پلنی تعریف نشده یا غیرفعال است).",
            show_alert=True,
        )
        return
    await callback.answer()
    min_gb, max_gb, _, _, _, _ = _custom_bounds(ui)
    data = await state.get_data()
    gb = int(data.get("custom_gb") or min_gb)
    gb = max(min_gb, min(max_gb, gb))
    await state.update_data(custom_gb=gb, custom_days=data.get("custom_days"))
    text = format_message(
        "✨ پلن دلخواه — حجم",
        f"حجم سرویس را انتخاب کنید ({min_gb} تا {max_gb} گیگ):\n"
        f"فعلی: <b>{gb}</b> گیگ",
    )
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=kb.custom_gb_keyboard(gb, ui))


@router.callback_query(F.data.in_({"shop:custom:gb:+", "shop:custom:gb:-"}))
async def custom_gb_step(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    ui = await get_all_settings(session)
    if not await _custom_available_for_users(session, ui):
        await callback.answer("پلن دلخواه در دسترس نیست", show_alert=True)
        return
    min_gb, max_gb, _, _, _, _ = _custom_bounds(ui)
    data = await state.get_data()
    gb = int(data.get("custom_gb") or min_gb)
    if callback.data.endswith("+"):
        gb = min(max_gb, gb + 1)
    else:
        gb = max(min_gb, gb - 1)
    await state.update_data(custom_gb=gb)
    await callback.answer()
    text = format_message(
        "✨ پلن دلخواه — حجم",
        f"حجم سرویس را انتخاب کنید ({min_gb} تا {max_gb} گیگ):\n"
        f"فعلی: <b>{gb}</b> گیگ",
    )
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=kb.custom_gb_keyboard(gb, ui))


@router.callback_query(F.data == "shop:custom:gb:input")
async def custom_gb_ask(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    ui = await get_all_settings(session)
    if not await _custom_available_for_users(session, ui):
        await callback.answer("پلن دلخواه در دسترس نیست", show_alert=True)
        return
    await callback.answer()
    min_gb, max_gb, _, _, _, _ = _custom_bounds(ui)
    await state.set_state(ShopStates.custom_gb_input)
    if callback.message:
        await callback.message.answer(
            f"حجم به گیگ را وارد کنید ({min_gb} تا {max_gb}):",
            reply_markup=kb.cancel_reply(),
        )


@router.message(ShopStates.custom_gb_input)
async def custom_gb_entered(message: Message, state: FSMContext, session: AsyncSession):
    ui = await get_all_settings(session)
    if (message.text or "").strip() == "انصراف":
        await state.set_state(None)
        await message.answer("لغو شد.", reply_markup=kb.back_home(ui))
        return
    min_gb, max_gb, _, _, _, _ = _custom_bounds(ui)
    try:
        gb = int(float((message.text or "").replace(",", "").replace("٬", "").strip()))
    except ValueError:
        await message.answer("عدد معتبر بفرستید")
        return
    if gb < min_gb or gb > max_gb:
        await message.answer(f"حجم باید بین {min_gb} تا {max_gb} باشد")
        return
    await state.set_state(None)
    await state.update_data(custom_gb=gb)
    await message.answer(
        format_message(
            "✨ پلن دلخواه — حجم",
            f"حجم انتخاب‌شده: <b>{gb}</b> گیگ",
        ),
        reply_markup=kb.custom_gb_keyboard(gb, ui),
    )


@router.callback_query(F.data == "shop:custom:gb:next")
async def custom_days_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    ui = await get_all_settings(session)
    if not await _custom_available_for_users(session, ui):
        await callback.answer("پلن دلخواه در دسترس نیست", show_alert=True)
        return
    await callback.answer()
    _, _, min_days, max_days, _, _ = _custom_bounds(ui)
    data = await state.get_data()
    gb = int(data.get("custom_gb") or _custom_bounds(ui)[0])
    days = int(data.get("custom_days") or min_days)
    days = max(min_days, min(max_days, days))
    await state.update_data(custom_gb=gb, custom_days=days)
    text = format_message(
        "✨ پلن دلخواه — مدت",
        f"حجم: <b>{gb}</b> گیگ\n"
        f"مدت را انتخاب کنید ({min_days} تا {max_days} روز):\n"
        f"فعلی: <b>{days}</b> روز",
    )
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=kb.custom_days_keyboard(days, ui))


@router.callback_query(F.data.in_({"shop:custom:days:+", "shop:custom:days:-"}))
async def custom_days_step(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    ui = await get_all_settings(session)
    if not await _custom_available_for_users(session, ui):
        await callback.answer("پلن دلخواه در دسترس نیست", show_alert=True)
        return
    _, _, min_days, max_days, _, _ = _custom_bounds(ui)
    data = await state.get_data()
    gb = int(data.get("custom_gb") or _custom_bounds(ui)[0])
    days = int(data.get("custom_days") or min_days)
    if callback.data.endswith("+"):
        days = min(max_days, days + 1)
    else:
        days = max(min_days, days - 1)
    await state.update_data(custom_days=days)
    await callback.answer()
    text = format_message(
        "✨ پلن دلخواه — مدت",
        f"حجم: <b>{gb}</b> گیگ\n"
        f"مدت را انتخاب کنید ({min_days} تا {max_days} روز):\n"
        f"فعلی: <b>{days}</b> روز",
    )
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=kb.custom_days_keyboard(days, ui))


@router.callback_query(F.data == "shop:custom:days:input")
async def custom_days_ask(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    ui = await get_all_settings(session)
    if not await _custom_available_for_users(session, ui):
        await callback.answer("پلن دلخواه در دسترس نیست", show_alert=True)
        return
    await callback.answer()
    _, _, min_days, max_days, _, _ = _custom_bounds(ui)
    await state.set_state(ShopStates.custom_days_input)
    if callback.message:
        await callback.message.answer(
            f"مدت به روز را وارد کنید ({min_days} تا {max_days}):",
            reply_markup=kb.cancel_reply(),
        )


@router.message(ShopStates.custom_days_input)
async def custom_days_entered(message: Message, state: FSMContext, session: AsyncSession):
    ui = await get_all_settings(session)
    if (message.text or "").strip() == "انصراف":
        await state.set_state(None)
        await message.answer("لغو شد.", reply_markup=kb.back_home(ui))
        return
    _, _, min_days, max_days, _, _ = _custom_bounds(ui)
    try:
        days = int((message.text or "").replace(",", "").replace("٬", "").strip())
    except ValueError:
        await message.answer("عدد معتبر بفرستید")
        return
    if days < min_days or days > max_days:
        await message.answer(f"مدت باید بین {min_days} تا {max_days} باشد")
        return
    data = await state.get_data()
    gb = int(data.get("custom_gb") or _custom_bounds(ui)[0])
    await state.set_state(None)
    await state.update_data(custom_days=days)
    await message.answer(
        format_message(
            "✨ پلن دلخواه — مدت",
            f"حجم: <b>{gb}</b> گیگ\nمدت انتخاب‌شده: <b>{days}</b> روز",
        ),
        reply_markup=kb.custom_days_keyboard(days, ui),
    )


@router.callback_query(F.data == "shop:custom:confirm")
async def custom_confirm(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    ui = await get_all_settings(session)
    if not await _custom_available_for_users(session, ui):
        await callback.answer("پلن دلخواه در دسترس نیست", show_alert=True)
        return
    data = await state.get_data()
    min_gb, _, min_days, _, price_gb, price_day = _custom_bounds(ui)
    gb = int(data.get("custom_gb") or min_gb)
    days = int(data.get("custom_days") or min_days)
    amount = calc_custom_plan_price(
        gb=gb, days=days, price_per_gb=price_gb, price_per_day=price_day
    )
    await callback.answer()
    from app.services.formatting import info_block, kv_line

    body = info_block(
        [
            kv_line("📦", "حجم", f"<b>{gb}</b> گیگ"),
            kv_line("⏱", "مدت", f"<b>{days}</b> روز"),
            kv_line("💰", "قیمت", f"<b>{format_toman(amount, get_settings().currency)}</b>"),
            f"<i>({price_gb:,} ت/گیگ + {price_day:,} ت/روز)</i>".replace(",", "٬"),
        ]
    )
    if callback.message:
        await safe_edit_text(callback.message, 
            format_message("✨ تأیید پلن دلخواه", body),
            reply_markup=kb.custom_confirm_keyboard(ui),
        )


async def _notify_new_order(bot, session, order, db_user, plan_name: str | None):
    try:
        from app.services.notifications import notify_new_order

        await notify_new_order(
            bot,
            session,
            order=order,
            user_tg_id=db_user.telegram_id,
            user_name=db_user.full_name or db_user.username,
            plan_name=plan_name,
        )
    except Exception:
        pass


@router.callback_query(F.data == "shop:custom:buy")
async def custom_buy(callback: CallbackQuery, session: AsyncSession, db_user: BotUser, state: FSMContext):
    ui = await get_all_settings(session)
    if not await _custom_available_for_users(session, ui):
        await callback.answer("پلن دلخواه در دسترس نیست", show_alert=True)
        return
    data = await state.get_data()
    min_gb, _, min_days, _, price_gb, price_day = _custom_bounds(ui)
    gb = float(data.get("custom_gb") or min_gb)
    days = int(data.get("custom_days") or min_days)
    expected = calc_custom_plan_price(
        gb=gb, days=days, price_per_gb=price_gb, price_per_day=price_day
    )
    if expected > 0 and not kb.any_checkout_method_enabled(ui):
        await callback.answer("هیچ روش پرداختی فعال نیست", show_alert=True)
        return
    try:
        order = await create_custom_order(
            session,
            user_id=db_user.id,
            data_limit_gb=gb,
            duration_days=days,
            reseller_id=db_user.reseller_id,
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    await state.clear()
    await callback.answer()

    if order.amount <= 0:
        from app.services.orders import deliver_order, revert_failed_free_delivery

        await mark_order_free_paid(session, order, db_user.id)
        try:
            order = await deliver_order(session, order)
        except Exception as e:
            try:
                await revert_failed_free_delivery(session, order)
            except Exception:
                pass
            if callback.message:
                await safe_edit_text(callback.message, 
                    format_message("❌ خطا در تحویل", str(e)),
                    reply_markup=kb.back_home(ui),
                )
            return
        if callback.message:
            await safe_edit_text(callback.message, 
                format_message("✅ فعال شد", f"سفارش #{order.id} تحویل شد."),
                reply_markup=kb.back_home(ui),
            )
        try:
            await send_delivery_to_user(callback.bot, db_user.telegram_id, session, None, order)
        except Exception:
            pass
        return

    text = format_message(
        f"🧾 سفارش #{order.id}",
        f"پلن دلخواه — {gb:g} گیگ / {days} روز\n"
        f"مبلغ قابل پرداخت:\n<b>{format_toman(order.amount, get_settings().currency)}</b>\n\n"
        "روش پرداخت را انتخاب کنید:",
    )
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=kb.pay_methods(order.id, ui))
    await _notify_new_order(callback.bot, session, order, db_user, "پلن دلخواه")


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
    from app.services.formatting import info_block, kv_line

    body = info_block(
        [
            plan.description or "",
            kv_line("⏱", "مدت", f"<b>{plan.duration_days}</b> روز"),
            kv_line("📦", "حجم", f"<b>{limit}</b>"),
            kv_line("💰", "قیمت", f"<b>{format_toman(plan.price, get_settings().currency)}</b>"),
        ]
    )
    text = format_message(f"💎 {plan.name}", body)
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=kb.plan_actions(plan.id, ui))


@router.callback_query(F.data.startswith("shop:buy:"))
async def shop_buy(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    ui = await get_all_settings(session)
    plan_id = int(callback.data.split(":")[-1])
    plan = await get_plan(session, plan_id)
    if not plan:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return
    if plan.price > 0 and not kb.any_checkout_method_enabled(ui):
        await callback.answer("هیچ روش پرداختی فعال نیست", show_alert=True)
        return

    try:
        order = await create_order(
            session,
            user_id=db_user.id,
            plan_id=plan_id,
            reseller_id=db_user.reseller_id,
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return

    await callback.answer()

    # Free / trial: deliver immediately
    if order.amount <= 0:
        from app.services.orders import deliver_order, revert_failed_free_delivery

        await mark_order_free_paid(session, order, db_user.id)
        try:
            order = await deliver_order(session, order)
        except Exception as e:
            try:
                await revert_failed_free_delivery(session, order)
            except Exception:
                pass
            if callback.message:
                await safe_edit_text(callback.message, 
                    format_message("❌ خطا در تحویل", str(e)),
                    reply_markup=kb.back_home(ui),
                )
            return
        if callback.message:
            await safe_edit_text(callback.message, 
                format_message("✅ فعال شد", f"سفارش #{order.id} تحویل شد."),
                reply_markup=kb.back_home(ui),
            )
        try:
            await send_delivery_to_user(callback.bot, db_user.telegram_id, session, None, order)
        except Exception:
            pass
        return

    text = format_message(
        f"🧾 سفارش #{order.id}",
        f"مبلغ قابل پرداخت:\n<b>{format_toman(order.amount, get_settings().currency)}</b>\n\n"
        "روش پرداخت را انتخاب کنید:",
    )
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=kb.pay_methods(order.id, ui))
    await _notify_new_order(callback.bot, session, order, db_user, plan.name if plan else None)


@router.callback_query(F.data.startswith("pay:discount:"))
async def ask_discount(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    ui = await get_all_settings(session)
    if not on(ui.get("pay_discount_enabled")):
        await callback.answer("کد تخفیف غیرفعال است", show_alert=True)
        return
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
    if kb.is_cancel_text(message.text):
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.back_home(ui))
        return
    code_raw = (message.text or "").strip()
    if not code_raw:
        await message.answer("کد تخفیف را به‌صورت متن بفرستید.")
        return
    data = await state.get_data()
    order = await session.get(Order, data.get("order_id"))
    await state.clear()
    if not order or order.user_id != db_user.id:
        await message.answer("سفارش معتبر نیست.")
        return
    from app.services.orders import apply_discount

    discount, code = await apply_discount(
        session, code_raw, order.amount + order.discount_amount
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
    if not on(ui.get("pay_wallet_enabled")):
        await callback.answer("این روش پرداخت غیرفعال است", show_alert=True)
        return
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
    if order.note and str(order.note).startswith("reseller_app:"):
        if callback.message:
            await safe_edit_text(callback.message, 
                format_message(
                    "✅ پرداخت ثبت شد",
                    "هزینه نمایندگی پرداخت شد.\nدرخواست شما برای تأیید ادمین ارسال شد.",
                ),
                reply_markup=kb.back_home(ui),
            )
        for aid in get_settings().admin_ids:
            try:
                app_id = int(str(order.note).split(":", 1)[1])
            except Exception:
                app_id = 0
            try:
                await callback.bot.send_message(
                    aid,
                    f"🤝 درخواست نمایندگی پرداخت‌شده — سفارش #{order.id}\n"
                    f"کاربر: {db_user.full_name or db_user.telegram_id}",
                    reply_markup=kb.reseller_app_review(app_id) if app_id else None,
                )
            except Exception:
                pass
        return

    if callback.message:
        try:
            await safe_edit_text(callback.message, 
                format_message("✅ خرید موفق", "سرویس در حال تحویل است…"),
                reply_markup=kb.back_home(ui),
            )
        except Exception:
            pass
    try:
        await send_delivery_to_user(
            callback.bot, db_user.telegram_id, session, None, order
        )
    except Exception:
        pass
    try:
        from app.services.notifications import notify_new_subscription

        plan = await get_plan(session, order.plan_id) if order.plan_id else None
        await notify_new_subscription(
            callback.bot,
            session,
            order=order,
            user_tg_id=db_user.telegram_id,
            user_name=db_user.full_name or db_user.username,
            plan_name=plan.name if plan else None,
            needs_approval=False,
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("pay:card:"))
async def pay_card_cb(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    ui = await get_all_settings(session)
    if not on(ui.get("pay_card_enabled")):
        await callback.answer("این روش پرداخت غیرفعال است", show_alert=True)
        return
    order_id = int(callback.data.split(":")[-1])
    order = await session.get(Order, order_id)
    if not order or order.user_id != db_user.id:
        await callback.answer("سفارش نامعتبر", show_alert=True)
        return
    try:
        payment = await start_card_payment(session, order, db_user.id)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    await callback.answer()
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
        await safe_edit_text(callback.message, 
            format_message("💳 کارت به کارت", body),
            reply_markup=kb.back_home(ui),
        )


@router.callback_query(F.data.startswith("pay:gateway:"))
async def pay_gateway_cb(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    ui = await get_all_settings(session)
    if not on(ui.get("pay_gateway_enabled")):
        await callback.answer("این روش پرداخت غیرفعال است", show_alert=True)
        return
    order_id = int(callback.data.split(":")[-1])
    order = await session.get(Order, order_id)
    if not order or order.user_id != db_user.id:
        await callback.answer("سفارش نامعتبر", show_alert=True)
        return
    try:
        payment = await start_method_payment(
            session, order, db_user.id, PaymentMethod.GATEWAY.value
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    await callback.answer()
    amount = format_toman(order.amount, get_settings().currency)
    name = ui.get("gateway_name") or "درگاه پرداخت"
    link = (ui.get("gateway_link") or "").strip()
    if link:
        try:
            link = link.format(amount=order.amount, order_id=order.id, payment_id=payment.id)
        except Exception:
            pass
    try:
        body = (ui.get("gateway_pay_text") or "").format(
            amount=amount, order_id=order.id, name=name
        )
    except Exception:
        body = f"مبلغ {amount} را از طریق {name} پرداخت کنید و رسید بفرستید."
    body += f"\n\n(پرداخت #{payment.id})"
    rows: list[list[InlineKeyboardButton]] = []
    if link.startswith("http://") or link.startswith("https://"):
        rows.append([InlineKeyboardButton(text=f"🌐 ورود به {name}", url=link)])
    rows.append([InlineKeyboardButton(text=ui.get("btn_back") or "بازگشت", callback_data="menu:home")])
    if callback.message:
        await safe_edit_text(callback.message, 
            format_message(f"🌐 {name}", body),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("pay:crypto:"))
async def pay_crypto_cb(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    ui = await get_all_settings(session)
    if not on(ui.get("pay_crypto_enabled")):
        await callback.answer("این روش پرداخت غیرفعال است", show_alert=True)
        return
    order_id = int(callback.data.split(":")[-1])
    order = await session.get(Order, order_id)
    if not order or order.user_id != db_user.id:
        await callback.answer("سفارش نامعتبر", show_alert=True)
        return
    address = (ui.get("crypto_address") or "").strip()
    if not address:
        await callback.answer("آدرس ولت تنظیم نشده — به ادمین اطلاع دهید", show_alert=True)
        return
    try:
        payment = await start_method_payment(
            session, order, db_user.id, PaymentMethod.CRYPTO.value
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    await callback.answer()
    amount = format_toman(order.amount, get_settings().currency)
    try:
        body = (ui.get("crypto_pay_text") or "").format(
            amount=amount,
            asset=ui.get("crypto_asset") or "USDT",
            network=ui.get("crypto_network") or "—",
            address=address,
        )
    except Exception:
        body = (
            f"مبلغ {amount}\n"
            f"{ui.get('crypto_asset') or 'USDT'} ({ui.get('crypto_network') or '—'})\n"
            f"<code>{address}</code>\n\nرسید را بفرستید."
        )
    body += f"\n\n(پرداخت #{payment.id})"
    if callback.message:
        await safe_edit_text(callback.message, 
            format_message("💎 رمزارز", body),
            reply_markup=kb.back_home(ui),
        )


@router.callback_query(F.data.startswith("pay:stars:"))
async def pay_stars_cb(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    from aiogram.types import LabeledPrice

    ui = await get_all_settings(session)
    if not on(ui.get("pay_stars_enabled")):
        await callback.answer("این روش پرداخت غیرفعال است", show_alert=True)
        return
    order_id = int(callback.data.split(":")[-1])
    order = await session.get(Order, order_id)
    if not order or order.user_id != db_user.id:
        await callback.answer("سفارش نامعتبر", show_alert=True)
        return
    try:
        payment = await start_method_payment(
            session, order, db_user.id, PaymentMethod.STARS.value
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return
    await callback.answer()
    try:
        rate = int(float(ui.get("stars_toman_per_star") or 500))
    except ValueError:
        rate = 500
    stars = stars_amount_for_toman(order.amount, rate)
    title = (ui.get("stars_title") or "خرید سرویس")[:32]
    desc = (ui.get("stars_description") or f"سفارش #{order.id}")[:255]
    try:
        await callback.bot.send_invoice(
            chat_id=db_user.telegram_id,
            title=title,
            description=desc,
            payload=f"stars:{payment.id}:{stars}",
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=stars)],
            provider_token="",
        )
        if callback.message:
            await safe_edit_text(callback.message, 
                format_message(
                    "⭐ استارز تلگرام",
                    f"فاکتور {stars} استارز برای سفارش #{order.id} ارسال شد.\n"
                    f"(معادل تقریبی {format_toman(order.amount, get_settings().currency)})",
                ),
                reply_markup=kb.back_home(ui),
            )
    except Exception as e:
        if callback.message:
            await callback.message.answer(f"خطا در ساخت فاکتور استارز: {e}")
