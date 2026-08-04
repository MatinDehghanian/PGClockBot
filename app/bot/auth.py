"""Shared bot authorization helpers (Phase C4 — aligned with Web authz)."""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.db.models import BotUser, Role


def is_platform_admin(user: BotUser | None) -> bool:
    """True when the Telegram user is a platform admin (role or ADMIN_IDS)."""
    if user is None:
        return False
    return user.role == Role.ADMIN.value or user.telegram_id in get_settings().admin_ids


def can_shop_feature(
    key: str,
    *,
    profile: Any = None,
    db_user: BotUser | None = None,
) -> bool:
    """Bot shop feature check — same source of truth as Web ``require_perm`` / ``can_shop``.

    Platform Owner/Admin → allow. Otherwise uses ``web_permissions`` via authz
    (never Owner fallback, never ``bot_permissions`` column).
    """
    from app.services.authz import shop_feature_allowed

    if is_platform_admin(db_user):
        return shop_feature_allowed(key=key, role="admin")
    role = None
    if db_user is not None:
        role = db_user.role
    return shop_feature_allowed(key=key, profile=profile, role=role)
