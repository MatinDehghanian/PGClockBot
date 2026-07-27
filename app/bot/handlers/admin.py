from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import get_settings
from app.db.models import BotUser, Order, OrderStatus, Payment, PaymentStatus, Plan, Role, Ticket, UserService
from app.services.formatting import (
    format_system_stats,
    format_toman,
    node_status_fa,
    order_status_fa,
    service_card,
)
from app.services.orders import approve_payment, deliver_order, reject_payment
from app.services.pasarguard import get_pg
from app.services.resellers import make_reseller
from app.services.tickets import get_ticket, list_open_tickets, reply_ticket
from app.services.users import get_setting, set_setting
from app.services.updates import local_version


def _plan_line(p: Plan) -> str:
    flag = "✅" if p.is_active else "⏸"
    tpl = f"تمپلیت #{p.pg_template_id}" if p.pg_template_id else "بدون تمپلیت"
    return (
        f"{flag} #{p.id} {p.name} — {format_toman(p.price, get_settings().currency)} "
        f"| {p.duration_days} روز | {tpl}"
    )

router = Router(name="admin")


class AdminStates(StatesGroup):
    add_plan_name = State()
    add_plan_price = State()
    add_plan_days = State()
    add_plan_gb = State()
    add_plan_template = State()
    set_card = State()
    set_card_holder = State()
    pg_search = State()
    make_reseller = State()
    ticket_reply = State()


def _is_admin(user: BotUser) -> bool:
    return user.role == Role.ADMIN.value or user.telegram_id in get_settings().admin_ids


@router.callback_query(F.data == "adm:home")
async def adm_home(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"🛠 <b>پنل ادمین</b>\nنسخه: <code>{local_version()}</code>",
            reply_markup=kb.admin_home(),
        )


@router.callback_query(F.data == "adm:dash")
async def adm_dash(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    users_count = await session.scalar(select(func.count()).select_from(BotUser)) or 0
    orders_count = await session.scalar(select(func.count()).select_from(Order)) or 0
    pending_pay = await session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(Payment.status == PaymentStatus.PENDING.value, Payment.receipt_file_id.is_not(None))
    ) or 0
    pending_orders = await session.scalar(
        select(func.count())
        .select_from(Order)
        .where(Order.status.in_([OrderStatus.AWAITING_APPROVAL.value, OrderStatus.PAID.value]))
    ) or 0
    services = await session.scalar(select(func.count()).select_from(UserService)) or 0
    text = (
        "📊 <b>داشبورد</b>\n\n"
        f"👥 کاربران: {users_count}\n"
        f"🛒 سفارش‌ها: {orders_count}\n"
        f"⏳ سفارش منتظر تأیید: {pending_orders}\n"
        f"🧾 رسید معلق: {pending_pay}\n"
        f"📦 سرویس‌ها: {services}\n"
        f"🔢 نسخه: {local_version()}"
    )
    rows = [
        [
            InlineKeyboardButton(text="🛒 سفارش‌ها", callback_data="adm:orders"),
            InlineKeyboardButton(text="🧾 رسیدها", callback_data="adm:payments"),
        ],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")],
    ]
    if callback.message:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


def _order_actions(order: Order, payment: Payment | None) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    can_decide = False
    if payment and payment.status == PaymentStatus.PENDING.value:
        can_decide = True
    elif order.status in {OrderStatus.PAID.value, OrderStatus.AWAITING_APPROVAL.value}:
        can_decide = True
    if can_decide and order.status not in {OrderStatus.DELIVERED.value, OrderStatus.REJECTED.value}:
        rows.append(
            [
                InlineKeyboardButton(text="✅ تأیید", callback_data=f"ordrev:ok:{order.id}"),
                InlineKeyboardButton(text="❌ رد", callback_data=f"ordrev:no:{order.id}"),
            ]
        )
    return rows


@router.callback_query(F.data == "adm:orders")
async def adm_orders(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    result = await session.execute(select(Order).order_by(Order.id.desc()).limit(12))
    orders = list(result.scalars().all())
    if not orders:
        if callback.message:
            await callback.message.edit_text("سفارشی نیست.", reply_markup=kb.admin_home())
        return
    rows = []
    for o in orders:
        label = f"#{o.id} · {order_status_fa(o.status)} · {format_toman(o.amount, get_settings().currency)}"
        rows.append([InlineKeyboardButton(text=label[:64], callback_data=f"adm:order:{o.id}")])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")])
    if callback.message:
        await callback.message.edit_text(
            "🛒 <b>سفارش‌ها</b>\nیکی را برای جزئیات و تأیید/رد انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("adm:order:"))
async def adm_order_view(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    order_id = int(callback.data.split(":")[-1])
    order = await session.get(Order, order_id)
    if not order:
        await callback.answer("یافت نشد", show_alert=True)
        return
    await callback.answer()
    user = await session.get(BotUser, order.user_id)
    plan = await session.get(Plan, order.plan_id) if order.plan_id else None
    pay = (
        await session.execute(
            select(Payment).where(Payment.order_id == order_id).order_by(Payment.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    who = (user.full_name or user.username or str(order.user_id)) if user else str(order.user_id)
    text = (
        f"🛒 <b>سفارش #{order.id}</b>\n\n"
        f"وضعیت: <b>{order_status_fa(order.status)}</b>\n"
        f"کاربر: {who}\n"
        f"پلن: {plan.name if plan else (order.plan_id or '—')}\n"
        f"مبلغ: {format_toman(order.amount, get_settings().currency)}\n"
        f"روش: {order.payment_method or '—'}\n"
    )
    if pay:
        text += f"پرداخت: #{pay.id} ({pay.status})\n"
    rows = _order_actions(order, pay)
    rows.append([InlineKeyboardButton(text="⬅️ لیست سفارش‌ها", callback_data="adm:orders")])
    if callback.message:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def _approve_order_bot(session: AsyncSession, order: Order, bot) -> str:
    pay = (
        await session.execute(
            select(Payment).where(Payment.order_id == order.id).order_by(Payment.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if order.status == OrderStatus.DELIVERED.value:
        return "قبلاً تحویل شده"
    if pay and pay.status == PaymentStatus.PENDING.value:
        delivered = await approve_payment(session, pay, reviewer_tg=0)
        try:
            from app.services.receipts import build_approved_user_text

            user = await session.get(BotUser, pay.user_id)
            if user:
                text, markup = await build_approved_user_text(session, pay, delivered or order)
                await bot.send_message(user.telegram_id, text, reply_markup=markup)
        except Exception:
            pass
        return "سفارش تأیید و تحویل شد"
    if order.status == OrderStatus.PAID.value or (
        pay and pay.status == PaymentStatus.APPROVED.value and order.status != OrderStatus.DELIVERED.value
    ):
        delivered = await deliver_order(session, order)
        if pay:
            try:
                from app.services.receipts import build_approved_user_text

                user = await session.get(BotUser, pay.user_id)
                if user:
                    text, markup = await build_approved_user_text(session, pay, delivered)
                    await bot.send_message(user.telegram_id, text, reply_markup=markup)
            except Exception:
                pass
        return "سفارش تحویل شد"
    raise ValueError("این سفارش هنوز قابل تأیید نیست (رسید لازم است)")


@router.callback_query(F.data.startswith("ordrev:ok:"))
async def order_approve_cb(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user) and db_user.role != Role.RESELLER.value:
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    if not _is_admin(db_user):
        await callback.answer("فقط ادمین", show_alert=True)
        return
    order_id = int(callback.data.split(":")[-1])
    order = await session.get(Order, order_id)
    if not order:
        await callback.answer("یافت نشد", show_alert=True)
        return
    try:
        msg = await _approve_order_bot(session, order, callback.bot)
        await callback.answer(msg, show_alert=True)
    except Exception as e:
        await callback.answer(str(e), show_alert=True)
        return
    await session.refresh(order)
    pay = (
        await session.execute(
            select(Payment).where(Payment.order_id == order_id).order_by(Payment.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    text = f"🛒 سفارش #{order.id}\nوضعیت: <b>{order_status_fa(order.status)}</b>\n✅ انجام شد"
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=kb.order_review(order.id) if order.status != OrderStatus.DELIVERED.value else InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ سفارش‌ها", callback_data="adm:orders")]]))
        except Exception:
            pass


@router.callback_query(F.data.startswith("ordrev:no:"))
async def order_reject_cb(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("فقط ادمین", show_alert=True)
        return
    order_id = int(callback.data.split(":")[-1])
    order = await session.get(Order, order_id)
    if not order:
        await callback.answer("یافت نشد", show_alert=True)
        return
    pay = (
        await session.execute(
            select(Payment).where(Payment.order_id == order_id).order_by(Payment.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if pay and pay.status == PaymentStatus.PENDING.value:
        await reject_payment(session, pay, reviewer_tg=db_user.telegram_id, note="bot reject")
        user = await session.get(BotUser, pay.user_id)
        if user:
            try:
                from app.services.formatting import format_message

                await callback.bot.send_message(
                    user.telegram_id,
                    format_message("❌ سفارش رد شد", f"سفارش #{order_id} رد شد."),
                )
            except Exception:
                pass
    else:
        order.status = OrderStatus.REJECTED.value
        await session.commit()
    await callback.answer("رد شد", show_alert=True)
    if callback.message:
        try:
            await callback.message.edit_text(
                f"🛒 سفارش #{order_id}\nوضعیت: <b>ردشده</b>",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="⬅️ سفارش‌ها", callback_data="adm:orders")]]
                ),
            )
        except Exception:
            pass


@router.callback_query(F.data == "adm:payments")
async def adm_payments(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    result = await session.execute(
        select(Payment)
        .where(
            Payment.status == PaymentStatus.PENDING.value,
            Payment.receipt_file_id.is_not(None),
        )
        .order_by(Payment.id.desc())
        .limit(15)
    )
    payments = list(result.scalars().all())
    if not payments:
        if callback.message:
            await callback.message.edit_text("رسید معلقی نیست.", reply_markup=kb.admin_home())
        return
    for p in payments:
        caption = f"پرداخت #{p.id} — {format_toman(p.amount, get_settings().currency)}"
        try:
            await callback.bot.send_photo(
                db_user.telegram_id,
                photo=p.receipt_file_id,
                caption=caption,
                reply_markup=kb.payment_review(p.id),
            )
        except Exception:
            await callback.bot.send_message(
                db_user.telegram_id, caption, reply_markup=kb.payment_review(p.id)
            )
    if callback.message:
        await callback.message.edit_text("رسیدها ارسال شد.", reply_markup=kb.admin_home())


@router.callback_query(F.data == "adm:plans")
async def adm_plans(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    result = await session.execute(select(Plan).order_by(Plan.sort_order, Plan.id))
    plans = list(result.scalars().all())
    lines = ["📦 <b>پلن‌ها</b>\n"] + [_plan_line(p) for p in plans]
    rows = [[InlineKeyboardButton(text="➕ پلن جدید", callback_data="adm:plan:add")]]
    for p in plans[:10]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{'⏸' if p.is_active else '▶️'} #{p.id}",
                    callback_data=f"adm:plan:toggle:{p.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")])
    if callback.message:
        await callback.message.edit_text(
            "\n".join(lines) or "پلنی نیست",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data == "adm:plan:add")
async def adm_plan_add(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.add_plan_name)
    if callback.message:
        await callback.message.answer("نام پلن را بفرستید:", reply_markup=kb.cancel_reply())


@router.message(AdminStates.add_plan_name)
async def plan_name(message: Message, state: FSMContext):
    if (message.text or "").strip() == "انصراف":
        await state.clear()
        await message.answer("لغو شد.")
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminStates.add_plan_price)
    await message.answer("قیمت به تومان:")


@router.message(AdminStates.add_plan_price)
async def plan_price(message: Message, state: FSMContext):
    try:
        price = int((message.text or "").replace(",", "").replace("٬", ""))
    except ValueError:
        await message.answer("عدد معتبر بفرستید")
        return
    await state.update_data(price=price)
    await state.set_state(AdminStates.add_plan_days)
    await message.answer("مدت به روز:")


@router.message(AdminStates.add_plan_days)
async def plan_days(message: Message, state: FSMContext):
    try:
        days = int(message.text or "30")
    except ValueError:
        await message.answer("عدد معتبر")
        return
    await state.update_data(days=days)
    await state.set_state(AdminStates.add_plan_gb)
    await message.answer("حجم به گیگ (برای نامحدود 0):")


@router.message(AdminStates.add_plan_gb)
async def plan_gb(message: Message, state: FSMContext):
    try:
        gb = float(message.text or "0")
    except ValueError:
        await message.answer("عدد معتبر")
        return
    await state.update_data(gb=None if gb <= 0 else gb)
    await state.set_state(AdminStates.add_plan_template)
    await message.answer("آیدی تمپلیت پاسارگارد (یا 0 برای ساخت دستی):")


@router.message(AdminStates.add_plan_template)
async def plan_tpl(message: Message, state: FSMContext, session: AsyncSession):
    try:
        tpl = int(message.text or "0")
    except ValueError:
        await message.answer("عدد معتبر")
        return
    data = await state.get_data()
    await state.clear()
    plan = Plan(
        name=data["name"],
        price=data["price"],
        duration_days=data["days"],
        data_limit_gb=data.get("gb"),
        pg_template_id=tpl or None,
        is_active=True,
    )
    session.add(plan)
    await session.commit()
    await message.answer(f"پلن #{plan.id} ساخته شد ✅", reply_markup=kb.admin_home())


@router.callback_query(F.data.startswith("adm:plan:toggle:"))
async def plan_toggle(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    plan = await session.get(Plan, int(callback.data.split(":")[-1]))
    if not plan:
        await callback.answer("یافت نشد", show_alert=True)
        return
    plan.is_active = not plan.is_active
    await session.commit()
    await callback.answer("بروز شد")
    result = await session.execute(select(Plan).order_by(Plan.sort_order, Plan.id))
    plans = list(result.scalars().all())
    lines = ["📦 <b>پلن‌ها</b>\n"] + [_plan_line(p) for p in plans]
    rows = [[InlineKeyboardButton(text="➕ پلن جدید", callback_data="adm:plan:add")]]
    for p in plans[:10]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{'⏸' if p.is_active else '▶️'} #{p.id}",
                    callback_data=f"adm:plan:toggle:{p.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")])
    if callback.message:
        await callback.message.edit_text(
            "\n".join(lines) or "پلنی نیست",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data == "adm:settings")
async def adm_settings(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    card = await get_setting(session, "card_number")
    holder = await get_setting(session, "card_holder")
    text = f"⚙️ تنظیمات\nکارت: <code>{card or '—'}</code>\nصاحب: {holder or '—'}"
    rows = [
        [InlineKeyboardButton(text="💳 تنظیم کارت", callback_data="adm:set:card")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")],
    ]
    if callback.message:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "adm:set:card")
async def set_card(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.set_card)
    if callback.message:
        await callback.message.answer("شماره کارت را بفرستید:")


@router.message(AdminStates.set_card)
async def save_card(message: Message, state: FSMContext, session: AsyncSession):
    await set_setting(session, "card_number", (message.text or "").strip())
    await state.set_state(AdminStates.set_card_holder)
    await message.answer("نام صاحب کارت:")


@router.message(AdminStates.set_card_holder)
async def save_card_holder(message: Message, state: FSMContext, session: AsyncSession):
    await set_setting(session, "card_holder", (message.text or "").strip())
    await state.clear()
    await message.answer("ذخیره شد ✅", reply_markup=kb.admin_home())


@router.callback_query(F.data == "adm:users")
async def adm_users(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    total = await session.scalar(select(func.count()).select_from(BotUser))
    orders = await session.scalar(select(func.count()).select_from(Order))
    text = f"👥 کاربران بات: {total}\n🧾 سفارش‌ها: {orders}"
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.admin_home())


@router.callback_query(F.data == "adm:resellers")
async def adm_resellers(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.make_reseller)
    if callback.message:
        await callback.message.answer(
            "آیدی عددی تلگرام کاربر را برای نماینده‌شدن بفرستید.\n\n"
            "مثال:\n"
            "<code>123456789 15 1</code>\n\n"
            "• عدد اول: آیدی تلگرام\n"
            "• عدد دوم: درصد کمیسیون (پیش‌فرض ۱۰)\n"
            "• عدد سوم: ۱ = اجازه تأیید رسید، ۰ یا خالی = بدون تأیید",
            reply_markup=kb.cancel_reply(),
        )


@router.message(AdminStates.make_reseller)
async def make_res(message: Message, state: FSMContext, session: AsyncSession):
    if (message.text or "").strip() == "انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.admin_home())
        return
    parts = (message.text or "").split()
    try:
        tg_id = int(parts[0])
        commission = int(parts[1]) if len(parts) > 1 else 10
        can_approve = len(parts) > 2 and parts[2] in {"1", "approve=1", "yes", "بله"}
    except ValueError:
        await message.answer(
            "فرمت نامعتبر است.\nمثال: <code>123456789 15 1</code>"
        )
        return
    result = await session.execute(select(BotUser).where(BotUser.telegram_id == tg_id))
    user = result.scalar_one_or_none()
    if not user:
        await message.answer("کاربر باید حداقل یک بار ربات را استارت کرده باشد.")
        return
    await make_reseller(session, user, commission_percent=commission, can_approve_receipts=can_approve)
    await state.clear()
    await message.answer(f"کاربر {tg_id} نماینده شد ✅", reply_markup=kb.admin_home())


@router.callback_query(F.data == "adm:tickets")
async def adm_tickets(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    tickets = await list_open_tickets(session)
    if not tickets:
        if callback.message:
            await callback.message.edit_text("تیکت بازی نیست.", reply_markup=kb.admin_home())
        return
    rows = [
        [InlineKeyboardButton(text=f"#{t.id} {t.subject[:24]}", callback_data=f"adm:ticket:{t.id}")]
        for t in tickets[:20]
    ]
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")])
    if callback.message:
        await callback.message.edit_text(
            "🎫 تیکت‌های باز:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("adm:ticket:"))
async def adm_ticket_view(callback: CallbackQuery, session: AsyncSession, db_user: BotUser, state: FSMContext):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    ticket = await get_ticket(session, int(callback.data.split(":")[-1]))
    if not ticket:
        await callback.answer("یافت نشد", show_alert=True)
        return
    await callback.answer()
    lines = [f"🎫 #{ticket.id} — {ticket.subject}"]
    for m in ticket.messages[-12:]:
        who = "پشتیبانی" if m.is_staff else "کاربر"
        lines.append(f"<b>{who}:</b> {m.body}")
    await state.set_state(AdminStates.ticket_reply)
    await state.update_data(ticket_id=ticket.id)
    if callback.message:
        await callback.message.edit_text("\n".join(lines))
        await callback.message.answer("پاسخ را بنویسید:", reply_markup=kb.cancel_reply())


@router.message(AdminStates.ticket_reply)
async def adm_ticket_reply(message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser):
    if (message.text or "").strip() == "انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.admin_home())
        return
    data = await state.get_data()
    ticket = await session.get(Ticket, data.get("ticket_id"))
    if not ticket:
        await state.clear()
        return
    await reply_ticket(session, ticket, message.text or "", db_user.telegram_id, is_staff=True)
    await state.clear()
    user = await session.get(BotUser, ticket.user_id)
    if user:
        try:
            await message.bot.send_message(
                user.telegram_id,
                f"💬 پاسخ پشتیبانی برای تیکت #{ticket.id}:\n{message.text}",
            )
        except Exception:
            pass
    await message.answer("ارسال شد ✅", reply_markup=kb.admin_home())


@router.callback_query(F.data == "adm:pg")
async def adm_pg(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("🖥 عملیات پاسارگارد", reply_markup=kb.pg_admin_keyboard())


@router.callback_query(F.data == "adm:pg:stats")
async def pg_stats(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    try:
        stats = await get_pg().get_system_stats()
    except Exception as e:
        if callback.message:
            await callback.message.edit_text(f"خطا: {e}", reply_markup=kb.pg_admin_keyboard())
        return
    text = "📊 <b>آمار سیستم</b>\n\n" + format_system_stats(stats)
    if callback.message:
        await callback.message.edit_text(text[:3500], reply_markup=kb.pg_admin_keyboard())


@router.callback_query(F.data == "adm:pg:nodes")
async def pg_nodes(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    try:
        nodes = await get_pg().get_nodes()
    except Exception as e:
        if callback.message:
            await callback.message.edit_text(f"خطا: {e}", reply_markup=kb.pg_admin_keyboard())
        return
    items = nodes if isinstance(nodes, list) else nodes.get("nodes", nodes.get("items", []))
    lines = ["🕸 <b>نودها</b>\n"]
    rows = []
    for n in items[:20]:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        name = n.get("name") or n.get("address") or nid
        status = node_status_fa(n.get("status") or n.get("connection_status"))
        lines.append(f"#{nid} {name} — {status}")
        if nid is not None:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"♻️ اتصال مجدد #{nid}",
                        callback_data=f"adm:pg:recon:{nid}",
                    )
                ]
            )
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:pg")])
    if callback.message:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("adm:pg:recon:"))
async def pg_recon(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    node_id = int(callback.data.split(":")[-1])
    try:
        await get_pg().reconnect_node(node_id)
        await callback.answer("درخواست اتصال مجدد ارسال شد ✅", show_alert=True)
    except Exception as e:
        await callback.answer(str(e), show_alert=True)


@router.callback_query(F.data == "adm:pg:search")
async def pg_search_start(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.pg_search)
    if callback.message:
        await callback.message.answer("یوزرنیم پاسارگارد را بفرستید:", reply_markup=kb.cancel_reply())


@router.message(AdminStates.pg_search)
async def pg_search(message: Message, state: FSMContext):
    if (message.text or "").strip() == "انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.pg_admin_keyboard())
        return
    username = (message.text or "").strip()
    try:
        user = await get_pg().get_user_by_username(username)
    except Exception as e:
        await message.answer(f"خطا: {e}")
        return
    await state.clear()
    uid = user.get("id")
    text = service_card(user)
    rows = [
        [
            InlineKeyboardButton(text="♻️ ریست حجم", callback_data=f"adm:pg:reset:{uid}"),
            InlineKeyboardButton(text="🚫 غیرفعال", callback_data=f"adm:pg:dis:{uid}"),
        ],
        [
            InlineKeyboardButton(text="✅ فعال", callback_data=f"adm:pg:en:{uid}"),
            InlineKeyboardButton(text="🔏 باطل‌کردن ساب", callback_data=f"adm:pg:rev:{uid}"),
        ],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:pg")],
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("adm:pg:reset:"))
async def pg_reset(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[-1])
    try:
        user = await get_pg().reset_user_by_id(uid)
        await callback.answer("ریست شد", show_alert=True)
        if callback.message:
            await callback.message.edit_text(service_card(user), reply_markup=kb.pg_admin_keyboard())
    except Exception as e:
        await callback.answer(str(e), show_alert=True)


@router.callback_query(F.data.startswith("adm:pg:dis:"))
async def pg_dis(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[-1])
    try:
        user = await get_pg().set_disabled_by_id(uid, True)
        await callback.answer("غیرفعال شد", show_alert=True)
        if callback.message:
            await callback.message.edit_text(service_card(user), reply_markup=kb.pg_admin_keyboard())
    except Exception as e:
        await callback.answer(str(e), show_alert=True)


@router.callback_query(F.data.startswith("adm:pg:en:"))
async def pg_en(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[-1])
    try:
        user = await get_pg().set_disabled_by_id(uid, False)
        await callback.answer("فعال شد", show_alert=True)
        if callback.message:
            await callback.message.edit_text(service_card(user), reply_markup=kb.pg_admin_keyboard())
    except Exception as e:
        await callback.answer(str(e), show_alert=True)


@router.callback_query(F.data.startswith("adm:pg:rev:"))
async def pg_rev(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[-1])
    try:
        user = await get_pg().revoke_sub_by_id(uid)
        await callback.answer("سابسکریپشن باطل شد", show_alert=True)
        if callback.message:
            await callback.message.edit_text(service_card(user), reply_markup=kb.pg_admin_keyboard())
    except Exception as e:
        await callback.answer(str(e), show_alert=True)
