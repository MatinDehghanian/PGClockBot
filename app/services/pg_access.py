from __future__ import annotations

"""Map PasarGuard admin-role permissions → lightweight web-panel feature keys.

Resellers never get PG settings / admin_roles / cores / api_keys in our UI.

Hybrid Owner ACL: platform web Owner keeps full *shop* power, but PasarGuard
menus/actions are clamped to the env ``PG_USERNAME`` role (fail-closed).
"""

import time
from typing import Any

# Our panel feature keys (shown in sidebar under «پاسارگارد»)
PG_FEATURE_KEYS = (
    "pg_overview",
    "pg_users",
    "pg_templates",
    "pg_groups",
    "pg_hosts",
    "pg_inbounds",
    "pg_nodes",
)

# Owner-only PG UI (admin management) — never granted from limited role maps.
PG_OWNER_ONLY_FEATURES = ("pg_admins",)

PG_FEATURE_LABELS: dict[str, str] = {
    "pg_overview": "نمای کلی",
    "pg_users": "کاربران",
    "pg_templates": "تمپلیت",
    "pg_groups": "گروه",
    "pg_hosts": "هاست",
    "pg_inbounds": "اینباند",
    "pg_nodes": "نود",
    "pg_admins": "ادمین",
}

# Short-lived cache: role_id → (monotonic_at, features, raw_role)
_ROLE_CACHE: dict[int, tuple[float, list[str], dict]] = {}
_ROLE_CACHE_TTL = 60.0

# Platform env-credential capability cache: key → (monotonic_at, payload)
_PLATFORM_CAPS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PLATFORM_CAPS_TTL = 60.0


def clear_platform_pg_capability_cache() -> None:
    """Drop cached Owner PG ACL (call after setup / PG credential changes)."""
    _PLATFORM_CAPS_CACHE.clear()


def _admin_looks_like_pg_owner(admin: dict | None, role: dict | None) -> bool:
    """True when PasarGuard marks this account as panel owner / sudo."""
    if isinstance(role, dict) and role.get("is_owner"):
        return True
    if not isinstance(admin, dict):
        return False
    if admin.get("is_owner") or admin.get("is_sudo") or admin.get("is_superuser"):
        return True
    nested = admin.get("role")
    if isinstance(nested, dict) and nested.get("is_owner"):
        return True
    return False


def full_pg_owner_features() -> list[str]:
    """Complete PG sidebar keys for a true PasarGuard owner account."""
    out = list(PG_FEATURE_KEYS)
    for k in PG_OWNER_ONLY_FEATURES:
        if k not in out:
            out.append(k)
    return out


async def resolve_platform_pg_capabilities(
    *,
    username: str | None = None,
    password: str | None = None,
    base_url: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Resolve PG menu/action ACL for platform env credentials (Hybrid Owner).

    Fail-closed: any probe/role failure → empty features (no PG UI).
    Does not elevate beyond the token of the given / env credentials.
    """
    from app.config import get_settings
    from app.services.pasarguard import PasarGuardClient, PasarGuardError

    settings = get_settings()
    uname = (username if username is not None else settings.pg_username or "").strip()
    pwd = (
        password if password is not None else (settings.pg_password or "")
    ).replace("\r", "").strip()
    # base_url override only for setup probe (temporary client)
    cache_key = f"{(base_url or settings.pg_base_url or '').rstrip('/')}|{uname.lower()}"
    now = time.monotonic()
    if use_cache and username is None and password is None and base_url is None:
        hit = _PLATFORM_CAPS_CACHE.get(cache_key)
        if hit and (now - hit[0]) < _PLATFORM_CAPS_TTL:
            return dict(hit[1])

    empty: dict[str, Any] = {
        "ok": False,
        "error": None,
        "username": uname or None,
        "pg_is_owner": False,
        "pg_role_id": None,
        "features": [],
        "role": None,
        "admin": None,
    }
    if not uname or not pwd:
        empty["error"] = "اعتبارنامه پاسارگارد ناقص است"
        return empty

    client: PasarGuardClient | None = None
    own_client = bool(username is not None or password is not None or base_url is not None)
    try:
        if own_client:
            # Temporary client for setup probe — do not touch global get_pg() singleton.
            from app.config import get_settings as _gs

            # PasarGuardClient reads base from settings; briefly not ideal.
            # Construct with explicit login overrides (token via password grant).
            client = PasarGuardClient(username=uname, password=pwd)
            if base_url:
                client.base_url = str(base_url).rstrip("/")
                # Rebind httpx client base
                import httpx

                old = client._client
                client._client = httpx.AsyncClient(
                    base_url=client.base_url,
                    timeout=30.0,
                    follow_redirects=False,
                )
                try:
                    await old.aclose()
                except Exception:
                    pass
        else:
            from app.services.pasarguard import get_pg

            client = get_pg()

        await client.ensure_token()
        admin = await client.get_admin(uname)
        if not isinstance(admin, dict):
            empty["error"] = "ادمین پاسارگارد یافت نشد"
            empty["ok"] = False
            if use_cache and not own_client:
                _PLATFORM_CAPS_CACHE[cache_key] = (now, dict(empty))
            return empty

        role_id = None
        nested_role = admin.get("role")
        if isinstance(nested_role, dict) and nested_role.get("id") is not None:
            try:
                role_id = int(nested_role["id"])
            except (TypeError, ValueError):
                role_id = None
        if role_id is None:
            for key in ("role_id", "admin_role_id"):
                if admin.get(key) is not None:
                    try:
                        role_id = int(admin[key])
                        break
                    except (TypeError, ValueError):
                        pass

        role: dict | None = None
        if role_id is not None:
            features, role = await resolve_reseller_pg_features(role_id)
        else:
            features, role = [], None
            # Some owner accounts expose permissions on the admin object itself
            if isinstance(nested_role, dict) and (
                nested_role.get("permissions") or nested_role.get("is_owner")
            ):
                role = nested_role
                features = map_pg_role_to_features(role)

        pg_is_owner = _admin_looks_like_pg_owner(admin, role)
        if pg_is_owner:
            features = full_pg_owner_features()
            if not role:
                role = {"is_owner": True, "permissions": {}}
            else:
                role = dict(role)
                role["is_owner"] = True

        payload = {
            "ok": True,
            "error": None,
            "username": uname,
            "pg_is_owner": pg_is_owner,
            "pg_role_id": role_id,
            "features": list(features or []),
            "role": role,
            "admin": admin,
        }
        if use_cache and not own_client:
            _PLATFORM_CAPS_CACHE[cache_key] = (now, dict(payload))
        return payload
    except PasarGuardError as e:
        empty["error"] = e.user_message(fallback=str(e))
        if use_cache and not own_client:
            _PLATFORM_CAPS_CACHE[cache_key] = (now, dict(empty))
        return empty
    except Exception as e:
        empty["error"] = str(e) or "خطا در خواندن نقش پاسارگارد"
        if use_cache and not own_client:
            _PLATFORM_CAPS_CACHE[cache_key] = (now, dict(empty))
        return empty
    finally:
        if own_client and client is not None:
            try:
                await client.close()
            except Exception:
                pass


async def enrich_platform_admin_staff(user: dict) -> dict:
    """Attach live PG ACL onto a web Owner / platform-admin staff dict."""
    import logging

    try:
        caps = await resolve_platform_pg_capabilities()
    except Exception:
        logging.getLogger(__name__).exception("enrich_platform_admin_staff probe failed")
        # Fail closed: shop Owner keeps panel access; PG menus stay empty.
        out = enrich_staff_pg_from_role(dict(user), [], None)
        out["pg_is_owner"] = False
        out["pg_capabilities_ok"] = False
        out["pg_capabilities_error"] = "بررسی دسترسی پاسارگارد ناموفق"
        return out
    features = list(caps.get("features") or [])
    role = caps.get("role") if isinstance(caps.get("role"), dict) else None
    out = enrich_staff_pg_from_role(user, features, role)
    out["pg_is_owner"] = bool(caps.get("pg_is_owner"))
    out["pg_capabilities_ok"] = bool(caps.get("ok"))
    out["pg_capabilities_error"] = caps.get("error")
    if caps.get("username"):
        out["pg_admin_username"] = caps["username"]
    if caps.get("pg_role_id") is not None:
        out["pg_role_id"] = caps["pg_role_id"]
    # Owner-equivalent: ensure action matrices are fully open
    if out.get("pg_is_owner"):
        out["pg_permissions"] = full_pg_owner_features()
        out["pg_actions"] = map_pg_role_actions({"is_owner": True})
        out["pg_user_actions"] = role_user_actions({"is_owner": True})
        out["pg_writes"] = map_pg_role_writes({"is_owner": True})
    return out


def _action_allowed(value: Any) -> bool:
    """PasarGuard action: True | {scope: N>0} → allowed; else denied."""
    if value is True:
        return True
    if isinstance(value, dict):
        try:
            return int(value.get("scope") or 0) > 0
        except (TypeError, ValueError):
            return False
    return False


def _resource_allows(perms: dict | None, resource: str, *actions: str) -> bool:
    if not isinstance(perms, dict):
        return False
    block = perms.get(resource)
    if not isinstance(block, dict):
        return False
    for action in actions:
        if _action_allowed(block.get(action)):
            return True
    return False


def map_pg_role_to_features(role: dict | None) -> list[str]:
    """Convert a PasarGuard AdminRoleResponse (or similar) into our feature keys."""
    if not role:
        return []
    if role.get("is_owner"):
        return list(PG_FEATURE_KEYS)

    raw = role.get("permissions") or {}
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    if not isinstance(raw, dict):
        return []

    out: list[str] = []
    if _resource_allows(raw, "system", "read"):
        out.append("pg_overview")
    if _resource_allows(raw, "users", "read", "read_simple", "create", "update", "delete"):
        out.append("pg_users")
    if _resource_allows(raw, "templates", "read", "read_simple", "create", "update", "delete"):
        out.append("pg_templates")
    if _resource_allows(raw, "groups", "read", "read_simple", "create", "update", "delete"):
        out.append("pg_groups")
    if _resource_allows(raw, "hosts", "read", "create", "update"):
        out.append("pg_hosts")
    # Inbounds are typically needed when managing groups — expose with groups or hosts read
    if "pg_groups" in out or "pg_hosts" in out or _resource_allows(raw, "groups", "read_simple"):
        out.append("pg_inbounds")
    if _resource_allows(raw, "nodes", "read", "read_simple", "reconnect", "stats"):
        out.append("pg_nodes")
    # Own-account overview (quota/users) mirrors native PasarGuard home for limited
    # roles that have resource access but lack system.read.
    if out and "pg_overview" not in out:
        out.insert(0, "pg_overview")
    # de-dupe preserve order
    seen: set[str] = set()
    ordered = []
    for k in out:
        if k not in seen and k in PG_FEATURE_KEYS:
            seen.add(k)
            ordered.append(k)
    return ordered


def role_user_actions(role: dict | None) -> dict[str, bool]:
    """Fine-grained user actions for the VPN users UI."""
    empty = {
        "create": False,
        "read": False,
        "update": False,
        "delete": False,
        "reset_usage": False,
        "revoke_sub": False,
        "disable": False,
        "enable": False,
    }
    if not role:
        return empty
    if role.get("is_owner"):
        return {k: True for k in empty}

    raw = role.get("permissions") or {}
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    if not isinstance(raw, dict):
        return empty
    users = raw.get("users") if isinstance(raw.get("users"), dict) else {}
    can_update = _action_allowed(users.get("update"))
    return {
        "create": _action_allowed(users.get("create")),
        "read": _action_allowed(users.get("read")) or _action_allowed(users.get("read_simple")),
        "update": can_update,
        "delete": _action_allowed(users.get("delete")),
        "reset_usage": _action_allowed(users.get("reset_usage")),
        "revoke_sub": _action_allowed(users.get("revoke_sub")),
        "disable": can_update,
        "enable": can_update,
    }


def map_pg_role_actions(role: dict | None) -> dict[str, dict[str, bool]]:
    """Exact PasarGuard action matrix per resource (create/update/delete/reconnect/…)."""
    resources = {
        "users": ("create", "update", "delete"),
        "templates": ("create", "update", "delete"),
        "groups": ("create", "update", "delete"),
        "hosts": ("create", "update", "delete"),
        "nodes": ("create", "update", "delete", "reconnect", "stats"),
    }
    empty = {res: {act: False for act in acts} for res, acts in resources.items()}
    if not role:
        return empty
    if role.get("is_owner"):
        return {res: {act: True for act in acts} for res, acts in resources.items()}
    raw = role.get("permissions") or {}
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    if not isinstance(raw, dict):
        return empty
    out: dict[str, dict[str, bool]] = {}
    for res, acts in resources.items():
        block = raw.get(res) if isinstance(raw.get(res), dict) else {}
        out[res] = {act: _action_allowed(block.get(act)) for act in acts}
    return out


def map_pg_role_writes(role: dict | None) -> dict[str, bool]:
    """Which PG resources the role may mutate (any of create/update/delete/reconnect)."""
    actions = map_pg_role_actions(role)
    return {res: any(flags.values()) for res, flags in actions.items()}


def role_access_limits(role: dict | None) -> dict:
    """Template/group allow-lists from role.access."""
    if not role:
        return {"require_template": False, "allowed_template_ids": None, "allowed_group_ids": None}
    access = role.get("access") or {}
    if hasattr(access, "model_dump"):
        access = access.model_dump()
    if not isinstance(access, dict):
        access = {}
    return {
        "require_template": bool(access.get("require_template")),
        "allowed_template_ids": access.get("allowed_template_ids"),
        "allowed_group_ids": access.get("allowed_group_ids"),
    }


async def resolve_reseller_pg_features(pg_role_id: int | None) -> tuple[list[str], dict | None]:
    """Fetch role from PasarGuard and return (feature_keys, raw_role). Cached ~60s."""
    if not pg_role_id:
        return [], None
    rid = int(pg_role_id)
    now = time.monotonic()
    hit = _ROLE_CACHE.get(rid)
    if hit and (now - hit[0]) < _ROLE_CACHE_TTL:
        return list(hit[1]), dict(hit[2]) if isinstance(hit[2], dict) else hit[2]

    from app.services.pasarguard import get_pg

    role = None
    try:
        role = await get_pg().get_admin_role(rid)
    except Exception:
        # Fallback: try list and find by id
        try:
            roles = await get_pg().get_admin_roles()
            role = next((r for r in roles if int(r.get("id") or 0) == rid), None)
        except Exception:
            return [], None
    if not isinstance(role, dict):
        return [], None
    features = map_pg_role_to_features(role)
    _ROLE_CACHE[rid] = (now, list(features), dict(role))
    return features, role


def enrich_staff_pg_from_role(user: dict, features: list[str], role: dict | None) -> dict:
    """Attach live PG ACL fields onto a staff dict (mutates a copy)."""
    out = dict(user)
    out["pg_permissions"] = list(features or [])
    if role:
        out["pg_writes"] = map_pg_role_writes(role)
        out["pg_actions"] = map_pg_role_actions(role)
        out["pg_user_actions"] = role_user_actions(role)
        out["pg_access"] = role_access_limits(role)
    return out


def staff_pg_writes(staff: dict) -> dict[str, bool]:
    """Broad write flags — Hybrid: Owner shop bypass does not imply PG writes."""
    from app.services.authz import authz_from_staff, can_pg_write_resource

    ctx = authz_from_staff(staff)
    keys = ("users", "templates", "groups", "hosts", "nodes")
    return {k: can_pg_write_resource(ctx, k) for k in keys}


def staff_pg_action(staff: dict, resource: str, action: str) -> bool:
    """True when staff may perform the exact PG action on a resource."""
    from app.services.authz import authz_from_staff, can_pg_action

    return can_pg_action(authz_from_staff(staff), resource, action)


def staff_user_actions(staff: dict) -> dict[str, bool]:
    from app.services.authz import authz_from_staff, can_pg_user_action

    ctx = authz_from_staff(staff)
    keys = (
        "create",
        "read",
        "update",
        "delete",
        "reset_usage",
        "revoke_sub",
        "disable",
        "enable",
    )
    return {k: can_pg_user_action(ctx, k) for k in keys}
