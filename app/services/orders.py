from __future__ import annotations

import secrets
import string
from typing import Optional

from sqlalchemy import select, update
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
from app.services.pg_quota import (
    PgQuotaError,
    assert_reseller_can_deliver,
    assert_reseller_can_renew,
)
from app.services.wallet import credit_wallet, debit_wallet


async def _reseller_pg_link(
    session: AsyncSession, reseller_id: int | None
) -> tuple[str | None, int | None]:
    """Return (pg_admin_username, pg_role_id) for a reseller shop owner."""
    if not reseller_id:
        return None, None
    profile = (
        await session.execute(
            select(ResellerProfile).where(ResellerProfile.user_id == int(reseller_id))
        )
    ).scalar_one_or_none()
    if not profile:
        return None, None
    return (
        (profile.pg_admin_username or "").strip() or None,
        int(profile.pg_role_id) if profile.pg_role_id else None,
    )


def _random_alnum(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _random_username(
    prefix: str = "clk",
    suffix: str = "",
    pattern: str | None = None,
    *,
    user_id: str | int | None = None,
) -> str:
    """Build a PG username from prefix/suffix or an optional pattern.

    Pattern placeholders: ``{prefix}``, ``{random}`` (8 alnum), ``{suffix}``, ``{id}``.
    """
    random_part = _random_alnum(8)
    id_part = "" if user_id is None else str(user_id)
    prefix = (prefix or "clk").strip() or "clk"
    suffix = suffix or ""
    if pattern and pattern.strip():
        try:
            return pattern.format(
                prefix=prefix,
                random=random_part,
                suffix=suffix,
                id=id_part,
            )
        except Exception:
            pass
    base = f"{prefix}_{random_part}"
    return f"{base}{suffix}" if suffix else base


async def generate_pg_username(
    session: AsyncSession,
    *,
    user_id: int | None = None,
) -> str:
    """Read username prefix/suffix/pattern from settings and generate a name."""
    from app.services.users import get_all_settings

    ui = await get_all_settings(session)
    prefix = ui.get("pg_username_prefix") or "clk"
    suffix = ui.get("pg_username_suffix") or ""
    pattern = ui.get("pg_username_pattern") or "{prefix}_{random}{suffix}"
    if not pattern:
        pattern = ui.get("pg_username_vars") or ""
    return _random_username(
        prefix=prefix or "clk",
        suffix=suffix or "",
        pattern=pattern or None,
        user_id=user_id,
    )


async def list_active_plans(
    session: AsyncSession,
    *,
    include_trial: bool = True,
    reseller_id: int | None = None,
) -> list[Plan]:
    """Active shop catalog.

    On a reseller-owned bot (or when reseller_id is passed), only that reseller's
    plans are returned. On the platform bot, only admin/platform plans.
    """
    from app.services.users import current_shop_reseller_id

    rid = reseller_id if reseller_id is not None else current_shop_reseller_id()
    q = select(Plan).where(Plan.is_active.is_(True))
    if rid:
        q = q.where(Plan.owner_reseller_id == rid)
    else:
        q = q.where(Plan.owner_reseller_id.is_(None))
    q = q.order_by(Plan.sort_order, Plan.id)
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
    from app.services.users import current_shop_reseller_id

    plan = await get_plan(session, plan_id)
    if not plan or not plan.is_active:
        raise ValueError("پلن یافت نشد")
    shop_rid = current_shop_reseller_id()
    if shop_rid:
        if int(plan.owner_reseller_id or 0) != int(shop_rid):
            raise ValueError("این پلن در این فروشگاه موجود نیست")
    elif plan.owner_reseller_id is not None:
        raise ValueError("این پلن در این فروشگاه موجود نیست")
    if plan.is_trial:
        # One free trial per user per shop (prevent callback re-buy)
        from app.services.users import current_shop_reseller_id

        shop_rid = current_shop_reseller_id()
        trial_q = (
            select(Order.id)
            .join(Plan, Plan.id == Order.plan_id)
            .where(
                Order.user_id == user_id,
                Plan.is_trial.is_(True),
                Order.status.in_(
                    [
                        OrderStatus.PAID.value,
                        OrderStatus.DELIVERED.value,
                        OrderStatus.AWAITING_APPROVAL.value,
                        OrderStatus.AWAITING_RECEIPT.value,
                    ]
                ),
            )
        )
        if shop_rid is not None:
            trial_q = trial_q.where(Order.reseller_id == int(shop_rid))
        else:
            # Platform shop: only platform-owned trial plans
            trial_q = trial_q.where(Plan.owner_reseller_id.is_(None))
        prior = await session.execute(trial_q.limit(1))
        if prior.scalar_one_or_none() is not None:
            raise ValueError("پلن تست رایگان را قبلاً دریافت کرده‌اید")
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


def calc_custom_plan_price(
    *,
    gb: float | int,
    days: int,
    price_per_gb: int,
    price_per_day: int,
) -> int:
    return max(0, int(gb) * int(price_per_gb) + int(days) * int(price_per_day))


async def create_custom_order(
    session: AsyncSession,
    *,
    user_id: int,
    data_limit_gb: float,
    duration_days: int,
    reseller_id: int | None = None,
    discount_code: str | None = None,
) -> Order:
    """Create an order for a user-chosen GB/days combo via an inactive temp Plan."""
    from app.services.users import current_shop_reseller_id, get_all_settings, on

    ui = await get_all_settings(session)
    if not on(ui.get("custom_plan_enabled")):
        raise ValueError("پلن دلخواه فعال نیست")
    # Require at least one active catalog plan (non-trial)
    catalog = await list_active_plans(session, include_trial=False)
    if not catalog:
        raise ValueError("پلن دلخواه بدون پلن فعال در فروشگاه در دسترس نیست")

    min_gb = int(float(ui.get("custom_plan_min_gb") or 1))
    max_gb = int(float(ui.get("custom_plan_max_gb") or 500))
    min_days = int(float(ui.get("custom_plan_min_days") or 1))
    max_days = int(float(ui.get("custom_plan_max_days") or 365))
    price_per_gb = int(float(ui.get("custom_plan_price_per_gb") or 1000))
    price_per_day = int(float(ui.get("custom_plan_price_per_day") or 500))

    gb = float(data_limit_gb)
    days = int(duration_days)
    if gb < min_gb or gb > max_gb:
        raise ValueError(f"حجم باید بین {min_gb} تا {max_gb} گیگ باشد")
    if days < min_days or days > max_days:
        raise ValueError(f"مدت باید بین {min_days} تا {max_days} روز باشد")

    amount = calc_custom_plan_price(
        gb=gb,
        days=days,
        price_per_gb=price_per_gb,
        price_per_day=price_per_day,
    )
    tpl_raw = (ui.get("custom_plan_template_id") or "").strip()
    tpl_id = int(tpl_raw) if tpl_raw.isdigit() else None
    group_ids = (ui.get("custom_plan_group_ids") or "").strip() or None
    shop_rid = current_shop_reseller_id()
    if shop_rid:
        # Do not inherit platform PG template/groups for reseller custom plans
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
        tpl_raw = own_map.get("custom_plan_template_id") or ""
        group_ids = own_map.get("custom_plan_group_ids") or None
        tpl_id = int(tpl_raw) if tpl_raw.isdigit() else None
        if not tpl_id and not group_ids:
            raise ValueError(
                "برای پلن دلخواه، تمپلیت یا گروه پاسارگارد اختصاصی فروشگاه را در تنظیمات مشخص کنید"
            )

    plan = Plan(
        name="پلن دلخواه",
        description=f"سفارشی {gb:g} گیگ / {days} روز",
        price=amount,
        duration_days=days,
        data_limit_gb=gb,
        pg_template_id=tpl_id,
        pg_group_ids=group_ids,
        owner_reseller_id=shop_rid,
        is_active=False,
        is_trial=False,
        sort_order=9999,
    )
    session.add(plan)
    await session.flush()

    discount, used_code = await apply_discount(session, discount_code, amount)
    order = Order(
        user_id=user_id,
        plan_id=plan.id,
        reseller_id=reseller_id,
        amount=max(0, amount - discount),
        discount_amount=discount,
        discount_code=used_code,
        status=OrderStatus.PENDING.value,
        note="custom",
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


_PAYABLE_ORDER_STATUSES = frozenset(
    {
        OrderStatus.PENDING.value,
        OrderStatus.REJECTED.value,
        OrderStatus.AWAITING_RECEIPT.value,
    }
)


async def pay_with_wallet(session: AsyncSession, order: Order, user) -> Order:
    if order.status == OrderStatus.DELIVERED.value:
        return order
    if order.status not in _PAYABLE_ORDER_STATUSES:
        raise ValueError("این سفارش قابل پرداخت با کیف پول نیست")
    payment: Payment | None = None
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
    await session.refresh(payment)
    try:
        if order.note and order.note.startswith("reseller_app:"):
            from app.services.resellers import mark_application_paid

            await mark_application_paid(session, order)
            order.status = OrderStatus.DELIVERED.value
            await session.commit()
            await session.refresh(order)
            return order
        if order.note and order.note.startswith("renew:"):
            if not (order.service_id and order.plan_id):
                raise ValueError("سفارش تمدید ناقص است")
            service = await session.get(UserService, order.service_id)
            plan = await session.get(Plan, order.plan_id)
            if not service or not plan:
                raise ValueError("سرویس یا پلن تمدید یافت نشد")
            return await apply_renewal(session, order, service, plan)
        return await deliver_order(session, order)
    except Exception:
        if order.amount > 0:
            await credit_wallet(session, user, order.amount, f"برگشت خرید ناموفق #{order.id}")
        order.status = OrderStatus.PENDING.value
        if payment is not None:
            payment.status = PaymentStatus.REJECTED.value
            payment.review_note = payment.review_note or "delivery_failed_refunded"
        await session.commit()
        raise


async def mark_order_free_paid(session: AsyncSession, order: Order, user_id: int) -> Order:
    """Mark a zero-amount order as paid with an approved payment row."""
    if order.amount > 0:
        raise ValueError("فقط سفارش رایگان قابل علامت‌گذاری رایگان است")
    if order.status not in _PAYABLE_ORDER_STATUSES:
        raise ValueError("این سفارش قابل پرداخت نیست")
    order.status = OrderStatus.PAID.value
    order.payment_method = PaymentMethod.WALLET.value
    session.add(
        Payment(
            order_id=order.id,
            user_id=user_id,
            amount=0,
            method=PaymentMethod.WALLET.value,
            status=PaymentStatus.APPROVED.value,
        )
    )
    await session.commit()
    await session.refresh(order)
    return order


async def revert_failed_free_delivery(session: AsyncSession, order: Order) -> None:
    """Undo mark_order_free_paid so the user can retry after a delivery failure."""
    order.status = OrderStatus.PENDING.value
    pays = await session.execute(
        select(Payment).where(
            Payment.order_id == order.id,
            Payment.status == PaymentStatus.APPROVED.value,
        )
    )
    for p in pays.scalars().all():
        p.status = PaymentStatus.REJECTED.value
        p.review_note = p.review_note or "delivery_failed"
    await session.commit()


async def start_card_payment(session: AsyncSession, order: Order, user_id: int) -> Payment:
    return await start_method_payment(session, order, user_id, PaymentMethod.CARD.value)


async def start_method_payment(
    session: AsyncSession,
    order: Order,
    user_id: int,
    method: str,
) -> Payment:
    if order.status not in _PAYABLE_ORDER_STATUSES:
        raise ValueError("این سفارش قابل پرداخت نیست")
    # Drop older pending payments when switching method
    if order.id:
        old = await session.execute(
            select(Payment).where(
                Payment.order_id == order.id,
                Payment.status == PaymentStatus.PENDING.value,
            )
        )
        for prev in old.scalars().all():
            prev.status = PaymentStatus.REJECTED.value
            prev.review_note = prev.review_note or "replaced by new payment method"
    order.payment_method = method
    order.status = OrderStatus.AWAITING_RECEIPT.value
    payment = Payment(
        order_id=order.id,
        user_id=user_id,
        amount=order.amount,
        method=method,
        status=PaymentStatus.PENDING.value,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


def stars_amount_for_toman(amount_toman: int, toman_per_star: int) -> int:
    rate = max(1, int(toman_per_star or 1))
    return max(1, (int(amount_toman) + rate - 1) // rate)

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
    payment_id = int(payment.id)
    # DB-only claim: disable autoflush so a dirty in-memory status cannot
    # rewrite the row to pending before the conditional UPDATE runs.
    with session.no_autoflush:
        claim = await session.execute(
            update(Payment)
            .where(
                Payment.id == payment_id,
                Payment.status == PaymentStatus.PENDING.value,
            )
            .values(status=PaymentStatus.APPROVED.value, reviewed_by=reviewer_tg)
            .execution_options(synchronize_session=False)
        )
    if claim.rowcount != 1:
        fresh = await session.get(Payment, payment_id)
        if fresh and fresh.status == PaymentStatus.APPROVED.value:
            if fresh.is_wallet_topup:
                return None
            if fresh.order_id:
                return await session.get(Order, fresh.order_id)
            return None
        raise ValueError("این پرداخت قابل تأیید نیست")
    await session.refresh(payment)

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
    # Reseller application fee — no VPN delivery; move application to review queue.
    if order.note and order.note.startswith("reseller_app:"):
        from app.services.resellers import mark_application_paid

        await mark_application_paid(session, order)
        order.status = OrderStatus.DELIVERED.value
        await session.commit()
        await session.refresh(order)
        return order
    # Renewal orders extend existing service instead of creating a new panel user.
    if order.note and order.note.startswith("renew:"):
        if not (order.service_id and order.plan_id):
            raise ValueError("سفارش تمدید ناقص است")
        service = await session.get(UserService, order.service_id)
        plan = await session.get(Plan, order.plan_id)
        if not service or not plan:
            raise ValueError("سرویس یا پلن تمدید یافت نشد")
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
    username = await generate_pg_username(session, user_id=order.user_id)

    pg_owner, pg_role_id = await _reseller_pg_link(session, order.reseller_id)
    data_limit = None
    expire = None
    if plan.data_limit_gb is not None:
        data_limit = int(plan.data_limit_gb * (1024**3))
    if plan.duration_days:
        import time

        expire = int(time.time()) + plan.duration_days * 86400

    if pg_owner:
        try:
            await assert_reseller_can_deliver(
                pg_admin_username=pg_owner,
                pg_role_id=pg_role_id,
                data_limit=data_limit,
                expire_ts=expire,
                from_template=bool(plan.pg_template_id),
            )
        except PgQuotaError as e:
            raise ValueError(e.message) from e

    pg_user: dict
    if plan.pg_template_id:
        payload = {
            "username": username,
            "user_template_id": plan.pg_template_id,
            "note": f"PGClockBot order #{order.id}",
        }
        pg_user = await pg.create_user_from_template(payload)
    else:
        from app.services.pasarguard import build_user_create_payload, parse_group_ids

        group_ids = parse_group_ids(getattr(plan, "pg_group_ids", None))
        if not group_ids:
            raise ValueError(
                "هیچ گروهی برای ساخت کاربر انتخاب نشده — در وب‌پنل برای پلن، گروه پاسارگارد را انتخاب کنید"
            )
        pg_user = await pg.create_user(
            build_user_create_payload(
                username=username,
                group_ids=group_ids,
                data_limit=data_limit,
                expire_ts=expire,
                note=f"PGClockBot order #{order.id}",
            )
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


async def create_wallet_topup(
    session: AsyncSession,
    user_id: int,
    amount: int,
    *,
    method: str = PaymentMethod.CARD.value,
) -> Payment:
    payment = Payment(
        user_id=user_id,
        amount=amount,
        method=method,
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
) -> Order:
    """Create a pending renewal order. Caller shows pay_methods (or uses pay_with_wallet)."""
    from app.services.users import current_shop_reseller_id

    if not plan or not plan.is_active:
        raise ValueError("پلن یافت نشد")
    if plan.is_trial:
        raise ValueError("پلن تست برای تمدید مجاز نیست")
    shop_rid = current_shop_reseller_id()
    if shop_rid:
        if int(plan.owner_reseller_id or 0) != int(shop_rid):
            raise ValueError("این پلن در این فروشگاه موجود نیست")
    elif plan.owner_reseller_id is not None:
        raise ValueError("این پلن در این فروشگاه موجود نیست")
    if service.bot_user_id != user_id:
        raise ValueError("سرویس متعلق به شما نیست")

    order = Order(
        user_id=user_id,
        plan_id=plan.id,
        amount=plan.price,
        status=OrderStatus.PENDING.value,
        note=f"renew:{service.id}",
        service_id=service.id,
        reseller_id=shop_rid,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def apply_renewal(session: AsyncSession, order: Order, service: UserService, plan: Plan) -> Order:
    pg = get_pg()
    if not service.pg_user_id:
        raise ValueError("service has no panel user")

    pg_owner, pg_role_id = await _reseller_pg_link(session, order.reseller_id)
    data_limit = int(plan.data_limit_gb * (1024**3)) if plan.data_limit_gb is not None else None
    expire = None
    if plan.duration_days:
        import time

        expire = int(time.time()) + plan.duration_days * 86400

    if pg_owner:
        try:
            await assert_reseller_can_renew(
                pg_admin_username=pg_owner,
                pg_role_id=pg_role_id,
                data_limit=data_limit,
                expire_ts=expire,
                from_template=bool(plan.pg_template_id),
            )
        except PgQuotaError as e:
            raise ValueError(e.message) from e

    if plan.pg_template_id:
        pg_user = await pg.modify_user_with_template(
            service.pg_user_id,
            {"user_template_id": plan.pg_template_id},
        )
    else:
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
