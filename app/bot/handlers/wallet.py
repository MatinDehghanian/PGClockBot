from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import get_settings
from app.db.models import BotUser, Payment, PaymentStatus
from app.services.formatting import format_message, format_toman
from app.services.orders import attach_receipt, create_wallet_topup
from app.services.receipts import process_receipt
from app.services.users import get_all_settings, get_setting
from app.services.wallet import list_transactions

router = Router(name="wallet")


class WalletStates(StatesGroup):
    topup_amount = State()
    waiting_receipt = State()


@router.callback_query(F.data == "wallet:home")
async def wallet_home(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    ui = await get_all_settings(session)
    text = format_message(
        "👛 کیف پول",
        f"موجودی فعلی:\n<b>{format_toman(db_user.wallet_balance, get_settings().currency)}</b>",
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=kb.wallet_keyboard(ui))


@router.callback_query(F.data == "wallet:tx")
async def wallet_tx(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    txs = await list_transactions(session, db_user.id)
    if not txs:
        body = "تراکنشی ثبت نشده است."
    else:
        lines = []
        for t in txs:
            sign = "+" if t.amount > 0 else ""
            lines.append(f"{sign}{t.amount:,} — {t.reason}".replace(",", "٬"))
        body = "\n".join(lines)
    ui = await get_all_settings(session)
    if callback.message:
        await callback.message.edit_text(
            format_message("📜 تراکنش‌ها", body),
            reply_markup=kb.wallet_keyboard(ui),
        )


@router.callback_query(F.data == "wallet:topup")
async def wallet_topup(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(WalletStates.topup_amount)
    if callback.message:
        await callback.message.answer(
            format_message("➕ شارژ کیف پول", "مبلغ شارژ را به تومان وارد کنید:"),
            reply_markup=kb.cancel_reply(),
        )


@router.message(WalletStates.topup_amount)
async def wallet_topup_amount(message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser):
    if (message.text or "").strip() == "انصراف":
        await state.clear()
        await message.answer(format_message("لغو شد", "عملیات لغو شد."), reply_markup=kb.back_home())
        return
    try:
        amount = int((message.text or "").replace(",", "").replace("٬", "").strip())
        if amount < 1000:
            raise ValueError
    except ValueError:
        await message.answer(format_message("⚠️ خطا", "مبلغ معتبر وارد کنید (حداقل ۱۰۰۰)."))
        return
    payment = await create_wallet_topup(session, db_user.id, amount)
    await state.set_state(WalletStates.waiting_receipt)
    await state.update_data(payment_id=payment.id)
    card = await get_setting(session, "card_number")
    holder = await get_setting(session, "card_holder")
    await message.answer(
        format_message(
            "💳 واریز",
            f"مبلغ {format_toman(amount, get_settings().currency)} را به کارت زیر واریز کنید:\n"
            f"<code>{card or '—'}</code>\n{holder or ''}\n\nسپس عکس رسید را بفرستید.",
        ),
        reply_markup=kb.cancel_reply(),
    )


@router.message(WalletStates.waiting_receipt, F.photo)
async def wallet_receipt_photo(message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser):
    data = await state.get_data()
    payment = await session.get(Payment, data.get("payment_id"))
    if not payment or payment.user_id != db_user.id:
        await state.clear()
        await message.answer(format_message("خطا", "پرداخت پیدا نشد."))
        return
    file_id = message.photo[-1].file_id
    await attach_receipt(session, payment, file_id)
    await state.clear()
    text = await process_receipt(
        session,
        payment,
        bot=message.bot,
        user_tg_id=message.from_user.id if message.from_user else None,
    )
    ui = await get_all_settings(session)
    await message.answer(text, reply_markup=kb.back_home(ui))


@router.message(F.photo)
async def generic_receipt(message: Message, session: AsyncSession, db_user: BotUser, state: FSMContext):
    """Attach photo to latest awaiting card payment for this user."""
    current = await state.get_state()
    if current:
        return
    result = await session.execute(
        select(Payment)
        .where(
            Payment.user_id == db_user.id,
            Payment.status == PaymentStatus.PENDING.value,
            Payment.receipt_file_id.is_(None),
        )
        .order_by(Payment.id.desc())
        .limit(1)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        return
    await attach_receipt(session, payment, message.photo[-1].file_id)
    text = await process_receipt(
        session,
        payment,
        bot=message.bot,
        user_tg_id=message.from_user.id if message.from_user else None,
    )
    ui = await get_all_settings(session)
    await message.answer(text, reply_markup=kb.back_home(ui))
