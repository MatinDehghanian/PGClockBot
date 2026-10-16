"""Shop ownership of a customer's services.

A service belongs to the shop that sold it (the shop of its fulfilling order),
not to whoever the customer is attributed to today. Every staff action and every
customer-facing service view re-checks this where the service is read or changed.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, Order, UserService

SERVICE_OUTSIDE_SHOP_MESSAGE = "این سرویس متعلق به فروشگاه دیگری است و از اینجا قابل مدیریت نیست"
_OWNER_UNKNOWN_MESSAGE = "مالکیت فروشگاه سرویس مشخص نیست"
_ORDER_REMARK_PREFIX = "order:"


def _order_id_from_remark(remark: str | None) -> int | None:
    """Order id of an ``order:N`` remark; None for any other remark; ValueError when malformed."""
    text = (remark or "").strip()
    if not text.startswith(_ORDER_REMARK_PREFIX):
        return None
    try:
        return int(text.split(":", 1)[1].split()[0])
    except (ValueError, IndexError):
        raise ValueError(_OWNER_UNKNOWN_MESSAGE) from None


async def service_shop_id(session: AsyncSession, service: UserService) -> int | None:
    """Use the fulfilling order's shop before first-touch user attribution."""
    order_id = _order_id_from_remark(service.remark)
    if order_id is not None:
        order = await session.get(Order, order_id)
        if not order or order.user_id != service.bot_user_id:
            raise ValueError(_OWNER_UNKNOWN_MESSAGE)
        return order.reseller_id
    user = await session.get(BotUser, service.bot_user_id)
    if not user:
        raise ValueError("کاربر یافت نشد")
    return user.reseller_id


async def assert_service_in_shop(
    session: AsyncSession, service: UserService, shop_id: int | None
) -> None:
    """Raise ``ValueError`` unless the service was sold by ``shop_id`` (None = platform).

    An unresolvable owner fails closed with the helper's own error.
    """
    if await service_shop_id(session, service) != shop_id:
        raise ValueError(SERVICE_OUTSIDE_SHOP_MESSAGE)


async def services_in_shop(
    session: AsyncSession, services: list[UserService], shop_id: int | None
) -> list[UserService]:
    """Keep the services ``shop_id`` sold, resolving all owners in two queries.

    Same rule as ``service_shop_id``; a service whose owner cannot be resolved is
    dropped so a list never shows something it could not authorize.
    """
    order_ids: dict[int, int] = {}
    for service in services:
        try:
            order_id = _order_id_from_remark(service.remark)
        except ValueError:
            continue
        if order_id is not None:
            order_ids[int(service.id)] = order_id
    orders: dict[int, Order] = {}
    if order_ids:
        rows = await session.scalars(select(Order).where(Order.id.in_(set(order_ids.values()))))
        orders = {int(order.id): order for order in rows}
    customer_ids = {int(s.bot_user_id) for s in services if int(s.id) not in order_ids}
    customer_shop: dict[int, int | None] = {}
    if customer_ids:
        pairs = await session.execute(
            select(BotUser.id, BotUser.reseller_id).where(BotUser.id.in_(customer_ids))
        )
        customer_shop = {int(uid): rid for uid, rid in pairs}

    kept: list[UserService] = []
    for service in services:
        sid = int(service.id)
        if sid in order_ids:
            order = orders.get(order_ids[sid])
            if order is None or order.user_id != service.bot_user_id:
                continue
            owner_shop = order.reseller_id
        elif int(service.bot_user_id) in customer_shop:
            owner_shop = customer_shop[int(service.bot_user_id)]
        else:
            continue
        if owner_shop == shop_id:
            kept.append(service)
    return kept


async def customer_may_use_service(
    session: AsyncSession, service: UserService | None, user_id: int, shop_id: int | None
) -> bool:
    """True when the service is this customer's and was sold by the bot they are using."""
    if service is None or int(service.bot_user_id) != int(user_id):
        return False
    try:
        return await service_shop_id(session, service) == shop_id
    except ValueError:
        return False


async def list_customer_services(
    session: AsyncSession, user_id: int, shop_id: int | None, *, limit: int | None = None
) -> list[UserService]:
    """The customer's services sold by ``shop_id``, newest first."""
    rows = list(
        await session.scalars(
            select(UserService).where(UserService.bot_user_id == int(user_id)).order_by(UserService.id.desc())
        )
    )
    kept = await services_in_shop(session, rows, shop_id)
    return kept[:limit] if limit else kept
