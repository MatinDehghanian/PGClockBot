"""Close a paid order that never got a service: refund it to the wallet, or record a manual delivery.

Such an order sits in «تحویل ناموفق» as «گیرکرده». Both actions claim the order with one atomic
UPDATE (status paid/delivering, no service, not touched for a while), so pressing twice, or two
admins at once, changes it once; the refund and the status change are one transaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, DeliveryFailure, Order, OrderStatus, Payment, PaymentStatus
from app.services.orders import is_mutation_order_note
from app.services.shop_scope import assert_order_retry_in_scope
from app.services.wallet import credit_wallet

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=10)
STUCK_STATUSES = (OrderStatus.PAID.value, OrderStatus.DELIVERING.value)
ORDER_NOT_FOUND = "سفارش پیدا نشد"
NOT_STUCK = "این سفارش دیگر گیرکرده نیست یا همین حالا در حال تحویل است؛ چند دقیقه بعد دوباره امتحان کنید"
MUTATION_ORDER = "این سفارش تمدید یا بسته است و از همان بخش خودش باید رسیدگی شود"


@dataclass(frozen=True, slots=True)
class Resolution:
    order_id: int
    user_id: int
    refunded: int
    shop_id: int | None


async def _load(session: AsyncSession, staff: dict, order_id: int) -> Order:
    order = await session.get(Order, int(order_id))
    if order is None:
        raise ValueError(ORDER_NOT_FOUND)
    assert_order_retry_in_scope(staff, order)
    if is_mutation_order_note(order.note):
        raise ValueError(MUTATION_ORDER)
    return order


async def _claim(session: AsyncSession, order: Order, new_status: str, now: datetime) -> None:
    result = await session.execute(
        update(Order)
        .where(
            Order.id == int(order.id),
            Order.status.in_(STUCK_STATUSES),
            Order.service_id.is_(None),
            Order.updated_at <= now - STALE_AFTER,
        )
        .values(status=new_status),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        await session.rollback()
        raise ValueError(NOT_STUCK)


async def _approved_payments(session: AsyncSession, order_id: int) -> list[Payment]:
    rows = await session.scalars(
        select(Payment).where(
            Payment.order_id == int(order_id),
            Payment.status == PaymentStatus.APPROVED.value,
            Payment.is_wallet_topup.is_(False),
        ).order_by(Payment.id)
    )
    return list(rows.all())


async def _close_failures(session: AsyncSession, order_id: int, now: datetime) -> None:
    await session.execute(
        update(DeliveryFailure)
        .where(DeliveryFailure.order_id == int(order_id), DeliveryFailure.resolved_at.is_(None))
        .values(resolved_at=now),
        execution_options={"synchronize_session": False},
    )


def _note(payment: Payment | None, text: str) -> None:
    if payment is not None:
        payment.review_note = f"{(payment.review_note or '').strip()} | {text}".strip(" |")[:2000]


async def cancel_and_refund(session: AsyncSession, staff: dict, order_id: int, *, actor: str, now: datetime | None = None) -> Resolution:
    """Cancel the order and return what was paid for it to the customer's wallet (once)."""
    now = now or datetime.now(timezone.utc)
    order = await _load(session, staff, order_id)
    user_id, shop_id = int(order.user_id), (int(order.reseller_id) if order.reseller_id else None)
    payments = await _approved_payments(session, order_id)
    amount = sum(max(0, int(p.amount or 0)) for p in payments)
    await _claim(session, order, OrderStatus.CANCELLED.value, now)
    if amount > 0:
        user = await session.get(BotUser, user_id)
        if user is None:
            await session.rollback()
            raise ValueError(ORDER_NOT_FOUND)
        await credit_wallet(session, user, amount, f"بازگشت وجه سفارش #{int(order_id)} (تحویل انجام نشد)", shop_id=shop_id, commit=False)
    _note(payments[-1] if payments else None, f"refunded {amount} to wallet by {actor}")
    await _close_failures(session, order_id, now)
    await session.commit()
    logger.info("stuck order %s cancelled and refunded amount=%s by=%s", order_id, amount, actor)
    return Resolution(order_id=int(order_id), user_id=user_id, refunded=amount, shop_id=shop_id)


async def mark_delivered_manually(session: AsyncSession, staff: dict, order_id: int, *, actor: str, now: datetime | None = None) -> Resolution:
    """Record that the admin delivered the service by hand; no money moves."""
    now = now or datetime.now(timezone.utc)
    order = await _load(session, staff, order_id)
    user_id, shop_id = int(order.user_id), (int(order.reseller_id) if order.reseller_id else None)
    payments = await _approved_payments(session, order_id)
    await _claim(session, order, OrderStatus.DELIVERED.value, now)
    _note(payments[-1] if payments else None, f"delivered manually, confirmed by {actor}")
    await _close_failures(session, order_id, now)
    await session.commit()
    logger.info("stuck order %s marked delivered manually by=%s", order_id, actor)
    return Resolution(order_id=int(order_id), user_id=user_id, refunded=0, shop_id=shop_id)


async def count_still_stuck(session: AsyncSession, order_ids: list[int]) -> int:
    """How many of these orders are still paid without a service (they stay in the stuck list)."""
    if not order_ids:
        return 0
    return int(
        await session.scalar(
            select(func.count()).select_from(Order).where(
                Order.id.in_([int(i) for i in order_ids]), Order.status.in_(STUCK_STATUSES), Order.service_id.is_(None)
            )
        )
        or 0
    )
