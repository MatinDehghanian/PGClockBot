"""«بررسی پرداخت» under a gateway checkout: the payer re-verifies their own payment.

The browser return to the panel often never arrives (the bank page needs VPN off), so
the customer comes back to the bot; this button lets them confirm the payment there
instead of waiting for the background poller.
"""

from __future__ import annotations

import logging
import time

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser
from app.services.payment_settlement import PspCheckOutcome, check_psp_payment
from app.services.redact import user_safe_error
from app.services.users import current_shop_reseller_id

logger = logging.getLogger(__name__)

router = Router(name="psp_check")

CHECK_PREFIX = "pspchk:"
CHECK_BUTTON_TEXT = "🔄 بررسی پرداخت"
# Each tap may call the gateway; one check per settlement per window is enough.
CHECK_THROTTLE_SECONDS = 10.0
_RECENT_LIMIT = 1000
_recent_checks: dict[int, float] = {}

OUTCOME_TEXT = {
    PspCheckOutcome.SETTLED: "✅ پرداخت شما تأیید شد. اگر سرویس یا شارژ را هنوز در چت نمی‌بینید، چند لحظه صبر کنید.",
    PspCheckOutcome.REVIEW: "⏳ پرداخت شما ثبت شده و فروشگاه آن را بررسی می‌کند؛ نتیجه در همین ربات اطلاع داده می‌شود.",
    PspCheckOutcome.PENDING: (
        "هنوز پرداختی در درگاه ثبت نشده است.\n"
        "اگر پرداخت را کامل کرده‌اید، چند لحظه بعد دوباره «بررسی پرداخت» را بزنید؛ "
        "تأیید خودکار هم در پس‌زمینه ادامه دارد."
    ),
    PspCheckOutcome.CLOSED: "این پرداخت دیگر باز نیست. برای خرید دوباره از منو اقدام کنید.",
}


def psp_check_button(settlement_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=CHECK_BUTTON_TEXT, callback_data=f"{CHECK_PREFIX}{int(settlement_id)}"
    )


def _throttled(settlement_id: int) -> bool:
    now = time.monotonic()
    last = _recent_checks.get(settlement_id)
    if last is not None and now - last < CHECK_THROTTLE_SECONDS:
        return True
    if len(_recent_checks) >= _RECENT_LIMIT:
        _recent_checks.pop(next(iter(_recent_checks)))
    _recent_checks[settlement_id] = now
    return False


@router.callback_query(F.data.regexp(rf"^{CHECK_PREFIX}\d+$"))
async def psp_check_cb(callback: CallbackQuery, session: AsyncSession, db_user: BotUser) -> None:
    settlement_id = int((callback.data or "").removeprefix(CHECK_PREFIX))
    if _throttled(settlement_id):
        await callback.answer("چند ثانیه بعد دوباره بزنید")
        return
    # Answer before the gateway call so Telegram does not expire the tap.
    await callback.answer("در حال بررسی پرداخت…")
    try:
        outcome = await check_psp_payment(
            session,
            settlement_id=settlement_id,
            user_id=int(db_user.id),
            shop_id=current_shop_reseller_id(),
        )
    except ValueError as exc:
        if callback.message:
            await callback.message.answer(user_safe_error(exc))
        return
    if callback.message is None:
        return
    if outcome in {PspCheckOutcome.SETTLED, PspCheckOutcome.REVIEW, PspCheckOutcome.CLOSED}:
        # The gateway and cancel buttons no longer apply to this payment.
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            logger.debug("psp check: checkout buttons already gone", exc_info=True)
    await callback.message.answer(OUTCOME_TEXT[outcome])
