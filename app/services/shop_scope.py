"""Fail-closed shop tenant scoping for web-panel staff.

Resellers (including PG admins provisioned with a reseller plan) must only
see/mutate rows owned by their ``bot_user_id``. Missing scope must NEVER fall
through to the platform/admin catalog or global counts.
"""

from __future__ import annotations

from typing import Any


class ShopScopeError(Exception):
    """Raised when a non-admin staff session has no valid shop owner id."""

    def __init__(self, message: str = "محدوده فروشگاه برای این حساب مشخص نیست"):
        self.message = message
        super().__init__(message)


def shop_owner_id(staff: dict | None) -> int | None:
    """Return positive reseller bot_user_id, or None for platform admin.

    - ``admin`` → None (platform scope)
    - ``reseller`` with valid bot_user_id → that id
    - anything else (pg_staff, broken session) → None meaning *no shop access*
      (callers must treat non-admin + None as empty/deny, never as platform)
    """
    if not staff:
        return None
    role = staff.get("role")
    if role == "admin":
        return None
    if role == "reseller":
        try:
            rid = int(staff.get("bot_user_id") or 0)
        except (TypeError, ValueError):
            return None
        return rid if rid > 0 else None
    return None


def is_platform_admin(staff: dict | None) -> bool:
    """Web session platform admin — independent of Telegram ADMIN_IDS (D4)."""
    from app.services.platform_identity import is_web_platform_admin

    return is_web_platform_admin(staff)


def require_shop_owner_id(staff: dict) -> int:
    """Reseller must have a shop id; admin must not call this for shop mutations."""
    if is_platform_admin(staff):
        raise ShopScopeError("ادمین اصلی از این مسیر فروشگاهی استفاده نمی‌کند")
    rid = shop_owner_id(staff)
    if not rid:
        raise ShopScopeError(
            "حساب شما به فروشگاه متصل نیست — دسترسی به داده‌های ادمین اصلی مجاز نیست"
        )
    return rid


def assert_order_in_scope(staff: dict, order: Any) -> None:
    if is_platform_admin(staff):
        return
    rid = require_shop_owner_id(staff)
    own = getattr(order, "reseller_id", None)
    try:
        own_i = int(own) if own is not None else 0
    except (TypeError, ValueError):
        own_i = 0
    if own_i != rid:
        raise ShopScopeError("دسترسی به این سفارش ندارید")


def empty_shop_stats() -> dict[str, int]:
    return {
        "users": 0,
        "orders": 0,
        "pending": 0,
        "services": 0,
        "revenue": 0,
        "plans": 0,
        "tickets": 0,
    }
