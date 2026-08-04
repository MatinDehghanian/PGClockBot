"""Phase C1 — tenant-safe PasarGuard read client selection.

Rules:
- Platform admin/Owner → owner client (`get_pg()`)
- Reseller with shop credentials → `get_pg_for_reseller` (never owner token)
- pg_staff (no stored PG password yet) → no read client until C5
  (fail closed: empty lists; no owner-token resource lists)

Does not change mutation client selection (`_staff_pg` / writes).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pasarguard import PasarGuardClient, PasarGuardError, get_pg, get_pg_for_reseller
from app.services.shop_scope import is_platform_admin, shop_owner_id

# Shown when a restricted principal cannot safely read PG resources.
PG_READ_ISOLATION_MSG = (
    "خواندن امن داده‌های پاسارگارد برای این حساب ممکن نیست "
    "— تا زمان همگام‌سازی اعتبارنامه، لیست‌ها خالی می‌مانند"
)


class PgReadDenied(Exception):
    """No tenant-safe PG read client for this principal."""

    def __init__(self, message: str = PG_READ_ISOLATION_MSG):
        self.message = message
        super().__init__(message)


async def staff_pg_read_client(
    session: AsyncSession | None,
    staff: dict | None,
) -> PasarGuardClient:
    """Return a PG client allowed for LIST/GET of tenant resources.

    Raises PgReadDenied when the principal must not use the owner token and
    has no own credentials (typical pg_staff until Phase C5).
    """
    if not staff:
        raise PgReadDenied("نشست نامعتبر است")
    if is_platform_admin(staff):
        return get_pg()

    rid = shop_owner_id(staff)
    if rid:
        if session is None:
            raise PgReadDenied("نشست پایگاه‌داده برای خواندن فروشگاه لازم است")
        try:
            return await get_pg_for_reseller(session, int(rid))
        except PasarGuardError as e:
            raise PgReadDenied(e.user_message(fallback=PG_READ_ISOLATION_MSG)) from e
        except Exception as e:
            raise PgReadDenied(str(e) or PG_READ_ISOLATION_MSG) from e

    # pg_staff / unknown: no owner-token reads in C1
    raise PgReadDenied(PG_READ_ISOLATION_MSG)


def staff_has_own_pg_read(staff: dict | None) -> bool:
    """True when principal can obtain a non-owner read client (reseller shop)."""
    if not staff:
        return False
    if is_platform_admin(staff):
        return True
    return shop_owner_id(staff) is not None


def trust_pg_list_scope(staff: dict | None) -> bool:
    """When True, allow-list None means keep client-scoped results (reseller own token).

    When False (owner-fetched or no client), allow-list None must fail closed.
    """
    if not staff or is_platform_admin(staff):
        return True
    return shop_owner_id(staff) is not None


def effective_pg_menu_keys(staff: dict | None) -> list[str]:
    """Menu keys that match what C1 can safely show as data.

    - Admin: full set from staff (caller may expand)
    - Reseller with shop: keep mapped pg_permissions (data via own client)
    - pg_staff / no shop: only overview (shows isolation error), hide list pages
    """
    if not staff:
        return []
    raw = list(staff.get("pg_permissions") or [])
    if is_platform_admin(staff):
        return raw
    if staff_has_own_pg_read(staff):
        return raw
    # No safe list reads — keep overview only if granted
    return [k for k in raw if k == "pg_overview"]


def empty_pg_read_payload() -> dict[str, Any]:
    return {
        "users": [],
        "templates": [],
        "groups": [],
        "hosts": [],
        "nodes": [],
        "inbounds": [],
        "inbound_tags": [],
        "details": None,
        "read_denied": True,
        "read_denied_msg": PG_READ_ISOLATION_MSG,
    }
