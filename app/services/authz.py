"""Unified authorization decision layer (Phase C0 / D4 / Hybrid Owner PG).

Web, Bot, and API must ask the same allow/deny questions here.
Shop feature keys use ``web_permissions`` (``bot_permissions`` is a mirrored
column only — never read for decisions).

Hybrid Owner:
- ``role==admin`` keeps full *shop* allow.
- PasarGuard pages/actions use ``pg_permissions`` / action matrices from the
  env ``PG_USERNAME`` role (fail-closed when empty). Enrichment lives in
  ``pg_access.enrich_platform_admin_staff`` (called from ``require_staff``).

This module does **not**:
- select PasarGuard clients
- enforce quotas / limits
- merge Web Owner (``web_admin.json``) with Bot ``ADMIN_IDS`` (D4 Q1 deferred;
  both remain session/bot ``role==\"admin\"`` for shop)
- invent Bot PG access for reseller/pg_staff (D4 Q2 — Web remains SoT)
- perform I/O (role fetch stays in require_staff / pg_access)

See ``docs/PHASE_D4_IDENTITY_MATRIX.md`` and ``app.services.platform_identity``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class PrincipalKind(str, Enum):
    """Logical principal. Owner and platform_admin both map from session role=admin in C0."""

    OWNER = "owner"
    PLATFORM_ADMIN = "platform_admin"
    RESELLER = "reseller"
    PG_STAFF = "pg_staff"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AuthzContext:
    kind: PrincipalKind
    role: str
    username: str | None = None
    shop_owner_id: int | None = None
    pg_admin_username: str | None = None
    pg_role_id: int | None = None
    shop_permissions: frozenset[str] = field(default_factory=frozenset)
    pg_permissions: frozenset[str] = field(default_factory=frozenset)
    pg_actions: Mapping[str, Mapping[str, bool]] = field(default_factory=dict)
    pg_user_actions: Mapping[str, bool] = field(default_factory=dict)
    pg_writes: Mapping[str, bool] = field(default_factory=dict)
    pg_access: Mapping[str, Any] = field(default_factory=dict)


def principal_kind_from_role(role: str | None) -> PrincipalKind:
    """Map session/bot role string → PrincipalKind.

    D4 Q1: Owner is still not distinguishable from platform admin at session
    level (``PrincipalKind.OWNER`` reserved; unused for ACL). Both use role
    ``admin`` for full *shop* allow; PG is clamped via ``pg_permissions``.
    """
    r = (role or "").strip()
    if r == "admin":
        return PrincipalKind.PLATFORM_ADMIN
    if r == "reseller":
        return PrincipalKind.RESELLER
    if r == "pg_staff":
        return PrincipalKind.PG_STAFF
    return PrincipalKind.UNKNOWN


def is_platform_admin(ctx: AuthzContext) -> bool:
    """True for Owner / platform admin (session role admin) — shop bypass."""
    return ctx.role == "admin" or ctx.kind in {
        PrincipalKind.OWNER,
        PrincipalKind.PLATFORM_ADMIN,
    }


def can_shop(ctx: AuthzContext, key: str) -> bool:
    """Shop feature key (dashboard, plans, orders, …). Admin always allowed."""
    if is_platform_admin(ctx):
        return True
    return key in ctx.shop_permissions


def can_pg_page(ctx: AuthzContext, key: str) -> bool:
    """PasarGuard panel page key (pg_users, pg_hosts, …).

    Hybrid: platform admin is *not* an automatic PG allow — uses mapped
    ``pg_permissions`` (fail-closed when empty / unresolved).
    """
    return key in ctx.pg_permissions


def can_pg_action(ctx: AuthzContext, resource: str, action: str) -> bool:
    """Exact PG resource action (e.g. hosts.create). Fail closed when matrix missing."""
    block = ctx.pg_actions.get(resource) if isinstance(ctx.pg_actions, Mapping) else None
    if isinstance(block, Mapping) and action in block:
        return bool(block.get(action))
    return False


def can_pg_user_action(ctx: AuthzContext, action: str) -> bool:
    """Fine-grained VPN user action. Matches prior staff_user_actions semantics."""
    raw = ctx.pg_user_actions if isinstance(ctx.pg_user_actions, Mapping) else {}
    if action in ("disable", "enable"):
        return bool(raw.get(action) or raw.get("update"))
    return bool(raw.get(action))


def can_pg_write_resource(ctx: AuthzContext, resource: str) -> bool:
    """Broad write flag (any mutate) — legacy pg_writes parity."""
    return bool(ctx.pg_writes.get(resource)) if isinstance(ctx.pg_writes, Mapping) else False


def _positive_int(value: Any) -> int | None:
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def authz_from_staff(staff: Mapping[str, Any] | None) -> AuthzContext:
    """Build context from a resolved web staff dict (post require_staff enrichment)."""
    if not staff:
        return AuthzContext(kind=PrincipalKind.UNKNOWN, role="")
    role = str(staff.get("role") or "")
    kind = principal_kind_from_role(role)
    shop_owner: int | None = None
    if role == "reseller":
        shop_owner = _positive_int(staff.get("bot_user_id"))
    pg_role = staff.get("pg_role_id")
    try:
        pg_role_id = int(pg_role) if pg_role is not None else None
    except (TypeError, ValueError):
        pg_role_id = None
    return AuthzContext(
        kind=kind,
        role=role,
        username=(str(staff.get("username")).strip() if staff.get("username") else None),
        shop_owner_id=shop_owner,
        pg_admin_username=(
            str(staff["pg_admin_username"]).strip() if staff.get("pg_admin_username") else None
        ),
        pg_role_id=pg_role_id,
        shop_permissions=frozenset(staff.get("permissions") or []),
        pg_permissions=frozenset(staff.get("pg_permissions") or []),
        pg_actions=dict(staff.get("pg_actions") or {}),
        pg_user_actions=dict(staff.get("pg_user_actions") or {}),
        pg_writes=dict(staff.get("pg_writes") or {}),
        pg_access=dict(staff.get("pg_access") or {}),
    )


def authz_from_shop_perm_list(
    perms: list[str] | None,
    *,
    role: str | None = None,
    active: bool = True,
) -> AuthzContext:
    """Build a shop-only context (bot/profile path after permission CSV resolved)."""
    if role == "admin":
        return AuthzContext(
            kind=PrincipalKind.PLATFORM_ADMIN,
            role="admin",
            shop_permissions=frozenset(perms or []),
        )
    if not active:
        return AuthzContext(
            kind=principal_kind_from_role(role or "reseller"),
            role=role or "reseller",
            shop_permissions=frozenset(),
        )
    return AuthzContext(
        kind=principal_kind_from_role(role or "reseller"),
        role=role or "reseller",
        shop_permissions=frozenset(perms or []),
    )


def resolve_shop_permissions_from_profile(profile: Any) -> list[str] | None:
    """Mirror has_perm profile → list resolution.

    Returns:
      None → profile missing/inactive (deny)
      list (possibly empty) → permission set to check

    Rules (Web + Bot must match):
      - ``web_permissions is None`` → DEFAULT + core shop keys
      - ``web_permissions == ""`` / empty parse → intentional deny (``[]``)
      - non-empty → parsed + core shop keys via ``with_shop_settings``
    Source of truth is ``web_permissions`` (``bot_permissions`` is a mirrored column).
    """
    if not profile or not getattr(profile, "is_active", False):
        return None
    from app.services.resellers import (
        DEFAULT_FEATURE_PERMS,
        parse_perms,
        with_shop_settings,
    )

    raw = getattr(profile, "web_permissions", None)
    if raw is None:
        return with_shop_settings(parse_perms(DEFAULT_FEATURE_PERMS))
    parsed = parse_perms(raw)
    return with_shop_settings(parsed) if parsed else parsed


def authz_from_profile(profile: Any, *, role: str | None = None) -> AuthzContext:
    """Build AuthzContext from a ResellerProfile (Bot + Web shop path)."""
    if role == "admin":
        return authz_from_shop_perm_list(None, role="admin")
    perms = resolve_shop_permissions_from_profile(profile)
    if perms is None:
        return authz_from_shop_perm_list([], role=role or "reseller", active=False)
    return authz_from_shop_perm_list(perms, role=role or "reseller", active=True)


def shop_feature_allowed(
    *,
    key: str,
    profile: Any = None,
    staff: Mapping[str, Any] | None = None,
    role: str | None = None,
) -> bool:
    """Single shop-feature decision for Web menus/API and Bot menus/actions.

    Prefer ``staff`` (already resolved session) when available; else ``profile``.
    """
    if key == "approve_receipts":
        key = "payments"
    if staff is not None:
        return can_shop(authz_from_staff(staff), key)
    if role == "admin":
        return can_shop(authz_from_shop_perm_list(None, role="admin"), key)
    return can_shop(authz_from_profile(profile, role=role), key)


def shop_menu_keys(
    *,
    profile: Any = None,
    staff: Mapping[str, Any] | None = None,
    role: str | None = None,
) -> frozenset[str]:
    """Feature keys visible in Web sidebar / Bot reseller hub (same set)."""
    if staff is not None:
        ctx = authz_from_staff(staff)
        if is_platform_admin(ctx):
            from app.services.resellers import FEATURE_PERMS

            return frozenset(k for k, _ in FEATURE_PERMS)
        return ctx.shop_permissions
    if role == "admin":
        from app.services.resellers import FEATURE_PERMS

        return frozenset(k for k, _ in FEATURE_PERMS)
    ctx = authz_from_profile(profile, role=role)
    if is_platform_admin(ctx):
        from app.services.resellers import FEATURE_PERMS

        return frozenset(k for k, _ in FEATURE_PERMS)
    return ctx.shop_permissions