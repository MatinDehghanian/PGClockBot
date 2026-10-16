"""Shop ownership guard for a customer's services.

A service belongs to the shop that sold it (the shop of its fulfilling order),
not to whoever the customer is attributed to today. Every staff action on a
service re-checks this at the point of mutation.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserService
from app.services.service_automation import service_shop_id

SERVICE_OUTSIDE_SHOP_MESSAGE = "این سرویس متعلق به فروشگاه دیگری است و از اینجا قابل مدیریت نیست"


async def assert_service_in_shop(
    session: AsyncSession, service: UserService, shop_id: int | None
) -> None:
    """Raise ``ValueError`` unless the service was sold by ``shop_id`` (None = platform).

    An unresolvable owner fails closed with the helper's own error.
    """
    if await service_shop_id(session, service) != shop_id:
        raise ValueError(SERVICE_OUTSIDE_SHOP_MESSAGE)
