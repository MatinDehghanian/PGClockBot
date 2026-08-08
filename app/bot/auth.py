"""Shared bot authorization helpers (Phase C4 / D4 / Hybrid Owner PG)."""

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


async def platform_pg_features() -> frozenset[str]:
    """Live PG menu keys for the env installer account (Hybrid fail-closed)."""
    from app.services.pg_access import resolve_platform_pg_capabilities

    caps = await resolve_platform_pg_capabilities()
    return frozenset(caps.get("features") or [])


async def can_platform_pg_page(db_user: BotUser | None, key: str) -> bool:
    """True when platform bot admin may open a PasarGuard bot surface."""
    if not is_platform_admin(db_user):
        return False
    return key in await platform_pg_features()


async def can_platform_pg_action(db_user: BotUser | None, resource: str, action: str) -> bool:
    if not is_platform_admin(db_user):
        return False
    from app.services.authz import authz_from_staff, can_pg_action
    from app.services.pg_access import enrich_staff_pg_from_role, resolve_platform_pg_capabilities

    caps = await resolve_platform_pg_capabilities()
    role = caps.get("role") if isinstance(caps.get("role"), dict) else None
    if caps.get("pg_is_owner"):
        role = {"is_owner": True}
    staff = enrich_staff_pg_from_role(
        {"role": "admin", "pg_is_owner": bool(caps.get("pg_is_owner"))},
        list(caps.get("features") or []),
        role,
    )
    return can_pg_action(authz_from_staff(staff), resource, action)


async def filtered_pg_reply_keyboard(db_user: BotUser | None = None, ui: dict | None = None):
    """Reply keyboard for PasarGuard submenu clamped to env PG role."""
    from app.bot import keyboards as kb

    feats = await platform_pg_features()
    can_create = await can_platform_pg_action(db_user, "users", "create")
    return kb.pg_reply_keyboard(ui, features=feats, can_create_user=can_create)
