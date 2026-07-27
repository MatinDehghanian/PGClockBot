from __future__ import annotations

import secrets
import string
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    BotUser,
    DiscountCode,
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Plan,
    ResellerProfile,
    UserService,
)
from app.services.pasarguard import extract_sub_token, get_pg
from app.services.wallet import credit_wallet, debit_wallet


def _random_username(prefix: str = "clk") -> str:
    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    return f"{prefix}_{suffix}"


async def list_active_plans(session: AsyncSession, *, include_trial: bool = True) -> list[Plan]:
    q = select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order, Plan.id)
    result = await session.execute(q)
    plans = list(result.scalars().all())
    if not include_trial:
        plans = [p for p in plans if not p.is_trial]
    return plans


async def get_plan(session: AsyncSession, plan_id: int) -> Optional[Plan]:
    return await session.get(Plan, plan_id)


async def apply_discount(session: AsyncSession, code: str | None, amount: int) -> tuple[int, str | None]:
    if not code:
        return 0, None
    result = await session.execute(
        select(DiscountCode).where(DiscountCode.code == code.upper(), DiscountCode.is_active.is_(True))
    )
    row = result.scalar_one_or_none()
    if not row:
        return 0, None
    if row.max_uses is not None and row.used_count >= row.max_uses:
        return 0, None
    discount = int(amount * row.percent / 100)
    return discount, row.code


async def create_order(
    session: AsyncSession,
    *,
    user_id: int,
    plan_id: int,
    reseller_id: int | None = None,
    discount_code: str | None = None,
) -> Order:
    plan = await get_plan(session, plan_id)
    if not plan or not plan.is_active:
        raise ValueError("پلن یافت نشد")
    discount, used_code = await apply_discount(session, discount_code, plan.price)
    order = Order(
        user_id=user_id,
        plan_id=plan.id,
        reseller_id=reseller_id,
        amount=max(0, plan.price - discount),
        discount_amount=discount,
        discount_code=used_code,
        status=OrderStatus.PENDING.value,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def pay_with_wallet(session: AsyncSession, order: Order, user) -> Order:
    if order.status == OrderStatus.DELIVERED.value:
        return order
    if order.amount > 0:
        await debit_wallet(session, user, order.amount, f"خرید سفارش #{order.id}")
    order.payment_method = PaymentMethod.WALLET.value
    order.status = OrderStatus.PAID.value
    payment = Payment(
        order_id=order.id,
        user_id=user.id,
        amount=order.amount,
        method=PaymentMethod.WALLET.value,
        status=PaymentStatus.APPROVED.value,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(order)
    try:
        return await deliver_order(session, order)
    except Exception:
        if order.amount > 0:
            await credit_wallet(session, user, order.amount, f"برگشت خرید ناموفق #{order.id}")
        order.status = OrderStatus.PENDING.value
        await session.commit()
        raise


async def start_card_payment(session: AsyncSession, order: Order, user_id: int) -> Payment:
    order.payment_method = PaymentMethod.CARD.value
    order.status = OrderStatus.AWAITING_RECEIPT.value
    payment = Payment(
        order_id=order.id,
        user_id=user_id,
        amount=order.amount,
        method=PaymentMethod.CARD.value,
        status=PaymentStatus.PENDING.value,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def attach_receipt(session: AsyncSession, payment: Payment, file_id: str) -> Payment:
    payment.receipt_file_id = file_id
    payment.status = PaymentStatus.PENDING.value
    if payment.order_id:
        order = await session.get(Order, payment.order_id)
        if order:
            order.status = OrderStatus.AWAITING_APPROVAL.value
    await session.commit()
    await session.refresh(payment)
    return payment


async def approve_payment(session: AsyncSession, payment: Payment, reviewer_tg: int) -> Order | None:
    if payment.status == PaymentStatus.APPROVED.value:
        if payment.is_wallet_topup:
            return None
        if payment.order_id:
            return await session.get(Order, payment.order_id)
        return None
    if payment.status != PaymentStatus.PENDING.value:
        raise ValueError("این پرداخت قابل تأیید نیست")

    payment.status = PaymentStatus.APPROVED.value
    payment.reviewed_by = reviewer_tg
    if payment.is_wallet_topup:
        user = await session.get(BotUser, payment.user_id)
        if user:
            await credit_wallet(session, user, payment.amount, f"شارژ کیف پول #{payment.id}")
        await session.commit()
        return None
    order = await session.get(Order, payment.order_id)
    if not order:
        await session.commit()
        return None
    if order.status == OrderStatus.DELIVERED.value:
        await session.commit()
        return order
    order.status = OrderStatus.PAID.value
    await session.commit()
    # Renewal orders extend existing service instead of creating a new panel user.
    if order.note and order.note.startswith("renew:") and order.service_id and order.plan_id:
        service = await session.get(UserService, order.service_id)
        plan = await session.get(Plan, order.plan_id)
        if service and plan:
            return await apply_renewal(session, order, service, plan)
    return await deliver_order(session, order)


async def reject_payment(session: AsyncSession, payment: Payment, reviewer_tg: int, note: str = "") -> None:
    payment.status = PaymentStatus.REJECTED.value
    payment.reviewed_by = reviewer_tg
    payment.review_note = note
    if payment.order_id:
        order = await session.get(Order, payment.order_id)
        if order:
            order.status = OrderStatus.REJECTED.value
    await session.commit()


async def deliver_order(session: AsyncSession, order: Order) -> Order:
    order = (
        await session.execute(
            select(Order)
            .where(Order.id == order.id)
            .options(selectinload(Order.plan), selectinload(Order.user))
        )
    ).scalar_one()
    plan = order.plan
    if not plan:
        raise ValueError("plan missing")

    pg = get_pg()
    username = _random_username()
    pg_user: dict
    if plan.pg_template_id:
        payload = {
            "username": username,
            "user_template_id": plan.pg_template_id,
            "note": f"PGClockBot order #{order.id}",
        }
        pg_user = await pg.create_user_from_template(payload)
    else:
        data_limit = None
        if plan.data_limit_gb is not None:
            data_limit = int(plan.data_limit_gb * (1024**3))
        expire = None
        if plan.duration_days:
            import time

            expire = int(time.time()) + plan.duration_days * 86400
        groups = await pg.get_groups_simple()
        group_ids = []
        if isinstance(groups, list):
            group_ids = [g["id"] for g in groups if isinstance(g, dict) and "id" in g]
        elif isinstance(groups, dict) and "groups" in groups:
            group_ids = [g["id"] for g in groups["groups"]]
        pg_user = await pg.create_user(
            {
                "username": username,
                "status": "active",
                "data_limit": data_limit,
                "expire": expire,
                "group_ids": group_ids[:1] if group_ids else None,
                "note": f"PGClockBot order #{order.id}",
            }
        )

    sub_url = pg_user.get("subscription_url")
    service = UserService(
        bot_user_id=order.user_id,
        plan_id=plan.id,
        pg_user_id=pg_user.get("id"),
        pg_username=pg_user.get("username", username),
        subscription_url=sub_url,
        subscription_token=extract_sub_token(sub_url),
        remark=f"order:{order.id}",
    )
    session.add(service)
    await session.flush()

    # assign owner for reseller if mapped
    if order.reseller_id and service.pg_user_id:
        profile = (
            await session.execute(
                select(ResellerProfile).where(ResellerProfile.user_id == order.reseller_id)
            )
        ).scalar_one_or_none()
        if profile and profile.pg_admin_username:
            try:
                await pg.set_owner_by_id(service.pg_user_id, profile.pg_admin_username)
            except Exception:
                pass
        if profile:
            commission = int(order.amount * profile.commission_percent / 100)
            profile.balance += commission

    if order.discount_code:
        disc = (
            await session.execute(
                select(DiscountCode).where(DiscountCode.code == order.discount_code)
            )
        ).scalar_one_or_none()
        if disc:
            disc.used_count += 1

    order.service_id = service.id
    order.status = OrderStatus.DELIVERED.value
    await session.commit()
    await session.refresh(order)
    return order


async def create_wallet_topup(session: AsyncSession, user_id: int, amount: int) -> Payment:
    payment = Payment(
        user_id=user_id,
        amount=amount,
        method=PaymentMethod.CARD.value,
        status=PaymentStatus.PENDING.value,
        is_wallet_topup=True,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def renew_service_with_plan(
    session: AsyncSession,
    *,
    user_id: int,
    service: UserService,
    plan: Plan,
    pay_wallet: bool,
    user,
) -> Order:
    order = Order(
        user_id=user_id,
        plan_id=plan.id,
        amount=plan.price,
        status=OrderStatus.PENDING.value,
        note=f"renew:{service.id}",
        service_id=service.id,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)

    if pay_wallet:
        try:
            if order.amount > 0:
                await debit_wallet(session, user, order.amount, f"تمدید سفارش #{order.id}")
            order.payment_method = PaymentMethod.WALLET.value
            order.status = OrderStatus.PAID.value
            session.add(
                Payment(
                    order_id=order.id,
                    user_id=user_id,
                    amount=order.amount,
                    method=PaymentMethod.WALLET.value,
                    status=PaymentStatus.APPROVED.value,
                )
            )
            await session.commit()
            return await apply_renewal(session, order, service, plan)
        except Exception:
            if order.amount > 0 and order.status == OrderStatus.PAID.value:
                await credit_wallet(session, user, order.amount, f"برگشت تمدید ناموفق #{order.id}")
            order.status = OrderStatus.PENDING.value
            await session.commit()
            raise

    await start_card_payment(session, order, user_id)
    await session.refresh(order)
    return order


async def apply_renewal(session: AsyncSession, order: Order, service: UserService, plan: Plan) -> Order:
    pg = get_pg()
    if not service.pg_user_id:
        raise ValueError("service has no panel user")
    if plan.pg_template_id:
        pg_user = await pg.modify_user_with_template(
            service.pg_user_id,
            {"user_template_id": plan.pg_template_id},
        )
    else:
        import time

        data_limit = int(plan.data_limit_gb * (1024**3)) if plan.data_limit_gb is not None else None
        expire = int(time.time()) + plan.duration_days * 86400 if plan.duration_days else None
        pg_user = await pg.modify_user_by_id(
            service.pg_user_id,
            {
                "status": "active",
                "data_limit": data_limit,
                "expire": expire,
            },
        )
    sub_url = pg_user.get("subscription_url") or service.subscription_url
    service.subscription_url = sub_url
    service.subscription_token = extract_sub_token(sub_url)
    service.plan_id = plan.id
    service.notified_expire = False
    service.notified_traffic = False
    order.status = OrderStatus.DELIVERED.value
    await session.commit()
    await session.refresh(order)
    return order
