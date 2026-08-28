"""Bulk table operations for web panel."""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, Order, OrderStatus, Payment, PaymentStatus, Ticket

logger = logging.getLogger(__name__)

MAX_BULK = 50


def parse_bulk_ids(raw: Iterable[str | int]) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for item in raw:
        try:
            n = int(item)
        except (TypeError, ValueError):
            continue
        if n <= 0 or n in seen:
            continue
        seen.add(n)
        out.append(n)
        if len(out) >= MAX_BULK:
            break
    return out


def _payment_in_scope(staff: dict, payment: Payment, order: Order | None) -> bool:
    from app.services.shop_scope import ShopScopeError, require_shop_owner_id

    if staff.get("role") == "admin":
        if payment.is_wallet_topup:
            return True
        if order and order.reseller_id is not None:
            return False
        return True
    try:
        rid = require_shop_owner_id(staff)
    except ShopScopeError:
        return False
    if payment.is_wallet_topup:
        return False
    if not order or order.reseller_id != rid:
        return False
    return True


async def bulk_toggle_block(
    session: AsyncSession,
    staff: dict,
    user_ids: list[int],
    *,
    block: bool,
) -> tuple[int, int]:
    from app.services.notifications import actor_label_from_staff, notify_account_edit
    from app.services.shop_scope import ShopScopeError, assert_bot_user_in_scope
    from app.services.users import is_protected_admin

    ids = parse_bulk_ids(user_ids)
    ok = fail = 0
    actor = actor_label_from_staff(staff)
    for uid in ids:
        user = await session.get(BotUser, uid)
        if not user:
            fail += 1
            continue
        try:
            assert_bot_user_in_scope(staff, user)
        except ShopScopeError:
            fail += 1
            continue
        if is_protected_admin(user):
            fail += 1
            continue
        if block and user.is_blocked:
            fail += 1
            continue
        if not block and not user.is_blocked:
            fail += 1
            continue
        user.is_blocked = block
        await session.flush()
        try:
            await notify_account_edit(
                session,
                user=user,
                event="block" if block else "unblock",
                actor=actor,
            )
        except Exception:
            logger.debug("bulk block notify failed uid=%s", uid, exc_info=True)
        ok += 1
    if ok:
        await session.commit()
    return ok, fail


async def bulk_close_bot_tickets(
    session: AsyncSession,
    staff: dict,
    ticket_ids: list[int],
) -> tuple[int, int]:
    from app.services.shop_scope import ShopScopeError, assert_bot_user_in_scope

    ids = parse_bulk_ids(ticket_ids)
    ok = fail = 0
    for tid in ids:
        ticket = await session.get(Ticket, tid)
        if not ticket or ticket.status == "closed":
            fail += 1
            continue
        user = await session.get(BotUser, ticket.user_id) if ticket.user_id else None
        if user:
            try:
                assert_bot_user_in_scope(staff, user)
            except ShopScopeError:
                fail += 1
                continue
        ticket.status = "closed"
        ok += 1
    if ok:
        await session.commit()
    return ok, fail


async def bulk_order_action(
    session: AsyncSession,
    staff: dict,
    order_ids: list[int],
    action: str,
) -> tuple[int, int]:
    from app.services.orders import (
        approve_payment,
        cancel_order,
        deliver_order,
        manual_fulfill_unpaid_order,
        reject_order,
    )
    from app.services.shop_scope import ShopScopeError, assert_order_in_scope

    ids = parse_bulk_ids(order_ids)
    ok = fail = 0
    for oid in ids:
        order = await session.get(Order, oid)
        if not order:
            fail += 1
            continue
        if order.reseller_id and staff.get("role") == "admin":
            fail += 1
            continue
        if staff.get("role") != "admin":
            try:
                assert_order_in_scope(staff, order)
            except ShopScopeError:
                fail += 1
                continue
        try:
            if action == "approve":
                if order.status == OrderStatus.DELIVERED.value:
                    fail += 1
                    continue
                result = await session.execute(
                    select(Payment)
                    .where(Payment.order_id == oid)
                    .order_by(Payment.id.desc())
                    .limit(1)
                )
                payment = result.scalar_one_or_none()
                if payment and payment.status == PaymentStatus.PENDING.value:
                    await approve_payment(session, payment, reviewer_tg=0)
                elif order.status == OrderStatus.PAID.value:
                    await deliver_order(session, order)
                elif order.status in {
                    OrderStatus.PENDING.value,
                    OrderStatus.AWAITING_RECEIPT.value,
                }:
                    await manual_fulfill_unpaid_order(session, order, note="web bulk approve")
                else:
                    fail += 1
                    continue
            elif action == "reject":
                await reject_order(session, order, note="web bulk reject")
            elif action == "cancel":
                await cancel_order(session, order)
            else:
                fail += 1
                continue
            ok += 1
        except Exception:
            logger.debug("bulk order action failed oid=%s", oid, exc_info=True)
            fail += 1
    if ok:
        await session.commit()
    return ok, fail


async def bulk_payment_action(
    session: AsyncSession,
    staff: dict,
    payment_ids: list[int],
    action: str,
) -> tuple[int, int]:
    from app.services.orders import approve_payment, reject_payment

    ids = parse_bulk_ids(payment_ids)
    ok = fail = 0
    for pid in ids:
        payment = await session.get(Payment, pid)
        if not payment or payment.status != PaymentStatus.PENDING.value:
            fail += 1
            continue
        order = await session.get(Order, payment.order_id) if payment.order_id else None
        if not _payment_in_scope(staff, payment, order):
            fail += 1
            continue
        try:
            if action == "approve":
                await approve_payment(session, payment, reviewer_tg=0)
            elif action == "reject":
                await reject_payment(session, payment, reviewer_tg=0)
            else:
                fail += 1
                continue
            ok += 1
        except Exception:
            logger.debug("bulk payment action failed pid=%s", pid, exc_info=True)
            fail += 1
    if ok:
        await session.commit()
    return ok, fail
