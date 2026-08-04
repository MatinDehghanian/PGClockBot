"""Shared bot authorization helpers (Phase C4 / D4 — aligned with Web authz)."""

from __future__ import annotations

from typing import Any

from app.db.models import BotUser


def is_platform_admin(user: BotUser | None) -> bool:
    """True when the Telegram user is a platform admin (role or ADMIN_IDS).

    Independent of Web ``web_admin.json`` (Phase D4). See
    ``app.services.platform_identity`` and ``docs/PHASE_D4_IDENTITY_MATRIX.md``.
    """
    from app.services.platform_identity import is_bot_platform_admin

    return is_bot_platform_admin(user)


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
