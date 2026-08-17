"""Principal management UI (Products 1–5).

GET / enable / disable use ``require_staff``; the service layer enforces
Owner vs Level-1 vs deny. L1 create stays on the existing Owner dependency.
L2 create wraps ``provision_level2_child`` only — no second provision path.
L2 Web identity wraps ``attach_level2_web_identity`` only — no second login path.
L2 Telegram bind/unbind wraps ``bind_l2_bot_telegram`` / ``unbind_l2_bot_telegram``.
"""

from __future__ import annotations

import logging
import uuid
from urllib.parse import quote

from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.identity_chrome import principal_capability_chips
from app.services.org_principals import (
    DEPTH_ONE,
    DEPTH_OWNER,
    DEPTH_TWO,
    get_principal,
    is_owner_principal,
)
from app.services.principal_l2_lifecycle import (
    actor_is_owner,
    disable_level2_principal,
    enable_level2_principal,
    get_level2_principal_detail,
    list_level2_principals,
    load_management_actor,
)
from app.services.principal_lifecycle import (
    PrincipalLifecycleError,
    disable_level1_principal,
    enable_level1_principal,
    get_level1_principal_detail,
    list_level1_principals,
    public_views_contain_secret,
)
from app.services.principal_child_provisioning import (
    ChildProvisionError,
    Level2ProvisionRequest,
    has_pg_admin_create_capability,
    provision_level2_child,
)
from app.services.principal_provisioning import (
    Level1ProvisionRequest,
    PrincipalProvisionError,
    owner_has_pg_admin_create_capability,
    provision_level1_principal,
)
from app.services.principal_web_identity import (
    PrincipalWebIdentityError,
    attach_level2_web_identity,
)
from app.services.bot_l2_bind import (
    L2BotBindError,
    bind_l2_bot_telegram,
    unbind_l2_bot_telegram,
)

log = logging.getLogger(__name__)


def _q(msg: str) -> str:
    return quote(str(msg), safe="")


def _web_status_label(raw: str | None) -> str:
    key = str(raw or "").strip().lower()
    if key == "active":
        return "فعال"
    if key == "inactive":
        return "غیرفعال"
    return "بدون هویت وب"


def _status_label(raw: str | None) -> str:
    if str(raw or "").strip() == "active":
        return "فعال"
    return "غیرفعال"


def _bot_label(raw: str | None) -> str:
    if str(raw or "").strip() == "bound":
        return "متصل"
    return "بدون اتصال"


def _safe_public(view, *, hierarchy_label: str) -> dict:
    data = view.to_public_dict()
    data["status_label"] = _status_label(getattr(view, "status", None))
    data["web_identity_label"] = _web_status_label(getattr(view, "web_identity_status", None))
    data["hierarchy_label"] = hierarchy_label
    data["bot_binding_label"] = _bot_label(data.get("bot_binding_status"))
    if "can_manage" not in data:
        data["can_manage"] = True
    return data


def _html_contains_secret(html: str) -> bool:
    blob = html or ""
    lower = blob.lower()
    if "pg_password_enc" in lower or "web_secret" in lower or "web_password_hash" in lower:
        return True
    if "gAAAAA" in blob:
        return True
    if "$2a$" in blob or "$2b$" in blob or "$2y$" in blob:
        return True
    return False


def _raise_if_forbidden(exc: PrincipalLifecycleError) -> None:
    if exc.code in {
        "forbidden",
        "unauthenticated",
        "not_found",
        "inactive_or_missing_principal",
    }:
        raise HTTPException(status_code=403, detail="forbidden") from exc


def _raise_if_l2_create_denied(exc: ChildProvisionError) -> None:
    """Hierarchy / actor / capability DENY — do not create via a second path."""
    if exc.code in {
        "forbidden",
        "unauthenticated",
        "not_found",
        "not_level1",
        "owner_creates_l1_only",
        "inactive_or_missing_principal",
        "parent_disabled",
        "parent_missing",
        "pg_capability_denied",
        "depth_forbidden",
        "cannot_become_owner",
    }:
        raise HTTPException(status_code=403, detail="forbidden") from exc


def _raise_if_web_attach_lifecycle_denied(exc: PrincipalLifecycleError) -> None:
    if exc.code in {
        "forbidden",
        "unauthenticated",
        "not_found",
        "inactive_or_missing_principal",
        "out_of_scope",
        "not_level2",
        "cannot_manage_owner",
        "cannot_manage_self",
        "parent_missing",
        "parent_disabled",
        "invalid_id",
        "hierarchy_invalid",
    }:
        raise HTTPException(status_code=403, detail="forbidden") from exc


def _raise_if_web_attach_denied(exc: PrincipalWebIdentityError) -> None:
    if exc.code in {
        "forbidden",
        "unauthenticated",
        "principal_missing",
        "principal_disabled",
        "parent_disabled",
        "parent_missing",
        "parent_invalid",
        "not_level2",
        "cannot_be_owner",
        "depth_invalid",
    }:
        raise HTTPException(status_code=403, detail="forbidden") from exc


def _can_attach_l2_web(detail: dict | None) -> bool:
    if not detail:
        return False
    return (
        str(detail.get("hierarchy_label") or "") == "سطح ۲"
        and str(detail.get("web_identity_status") or "") == "none"
        and bool(detail.get("can_manage"))
        and str(detail.get("status") or "") == "active"
    )


def _can_attach_l2_telegram(detail: dict | None) -> bool:
    if not detail:
        return False
    return (
        str(detail.get("hierarchy_label") or "") == "سطح ۲"
        and str(detail.get("bot_binding_status") or "") == "unbound"
        and bool(detail.get("can_manage"))
        and str(detail.get("status") or "") == "active"
    )


def _can_detach_l2_telegram(detail: dict | None) -> bool:
    if not detail:
        return False
    return (
        str(detail.get("hierarchy_label") or "") == "سطح ۲"
        and str(detail.get("bot_binding_status") or "") == "bound"
        and bool(detail.get("can_manage"))
        and str(detail.get("status") or "") == "active"
    )


def _raise_if_l2_bind_denied(exc: L2BotBindError) -> None:
    if exc.code in {
        "unauthenticated",
        "not_authorized",
        "not_direct_child",
        "out_of_scope",
        "principal_missing",
        "principal_disabled",
        "parent_disabled",
        "parent_missing",
        "not_level2",
        "cannot_bind_owner",
        "admin_ids_collision",
        "reseller_collision",
        "binding_collision",
        "already_bound",
        "duplicate_bot_user_id",
    }:
        raise HTTPException(status_code=403, detail="forbidden") from exc


async def _l1_pg_client(session: AsyncSession, staff: dict) -> Any | None:
    """L1/L2 Principal PG client — never Owner ``get_pg()``."""
    try:
        pid = int(staff.get("org_principal_id") or 0)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    try:
        from app.services.pasarguard import get_pg_for_principal

        return await get_pg_for_principal(session, principal_id=pid)
    except Exception:
        return None


async def _chips_for_role_id(
    role_id: int | None, *, client: Any | None = None
) -> list[str]:
    if role_id is None or client is None:
        return []
    try:
        rid = int(role_id)
    except (TypeError, ValueError):
        return []
    if rid <= 0:
        return []
    try:
        from app.services.pg_access import resolve_reseller_pg_features

        features, _role = await resolve_reseller_pg_features(rid, client=client)
    except Exception:
        return []
    if not features:
        return []
    return principal_capability_chips({"pg_permissions": list(features)})


async def _disable_managed(session, staff, principal_id: int):
    row = await get_principal(session, int(principal_id))
    if row is None:
        raise PrincipalLifecycleError("Principal یافت نشد", code="not_found")
    if is_owner_principal(row) or int(row.depth) == DEPTH_OWNER:
        raise PrincipalLifecycleError(
            "نمی‌توان مالک را غیرفعال کرد",
            code="cannot_disable_owner",
        )
    if int(row.depth) == DEPTH_ONE:
        return await disable_level1_principal(session, staff, int(principal_id))
    if int(row.depth) == DEPTH_TWO:
        return await disable_level2_principal(session, staff, int(principal_id))
    raise PrincipalLifecycleError("Principal قابل مدیریت نیست", code="invalid_depth")


async def _enable_managed(session, staff, principal_id: int):
    row = await get_principal(session, int(principal_id))
    if row is None:
        raise PrincipalLifecycleError("Principal یافت نشد", code="not_found")
    if is_owner_principal(row) or int(row.depth) == DEPTH_OWNER:
        raise PrincipalLifecycleError(
            "نمی‌توان مالک را مدیریت کرد",
            code="cannot_manage_owner",
        )
    if int(row.depth) == DEPTH_ONE:
        return await enable_level1_principal(session, staff, int(principal_id))
    if int(row.depth) == DEPTH_TWO:
        return await enable_level2_principal(session, staff, int(principal_id))
    raise PrincipalLifecycleError("Principal قابل مدیریت نیست", code="invalid_depth")


def register_principal_pages(app, *, render, require_admin, get_db, require_staff=None):
    staff_dep = require_staff or require_admin

    def _filter_picker_roles(roles) -> list[dict]:
        """Live PG roles for a create form. Owner-equivalent PG roles omitted."""
        out: list[dict] = []
        for role in roles or []:
            if not isinstance(role, dict):
                continue
            if role.get("is_owner"):
                continue
            rid = role.get("id")
            try:
                rid_i = int(rid)
            except (TypeError, ValueError):
                continue
            name = role.get("name")
            out.append(
                {
                    "id": rid_i,
                    "name": str(name).strip() if name else str(rid_i),
                }
            )
        return out

    async def _pg_roles_for_picker() -> list[dict]:
        """Live PasarGuard roles for Owner L1 create. Owner-equivalent roles omitted."""
        try:
            from app.services.pasarguard import get_pg

            roles = await get_pg().get_admin_roles()
        except Exception:
            log.debug("principal create: admin roles unavailable", exc_info=True)
            return []
        return _filter_picker_roles(roles)

    async def _l2_pg_roles_for_picker(session: AsyncSession, staff: dict) -> list[dict]:
        """Live PG roles from the authenticated L1's own PG client — not Owner env."""
        try:
            from app.services.pasarguard import get_pg_for_principal

            pid = int(staff.get("org_principal_id") or 0)
            if pid <= 0:
                return []
            pg = await get_pg_for_principal(session, principal_id=pid)
            roles = await pg.get_admin_roles()
        except Exception:
            log.debug("l2 create: parent admin roles unavailable", exc_info=True)
            return []
        return _filter_picker_roles(roles)

    def _role_name_map(roles: list[dict]) -> dict[int, str]:
        return {int(r["id"]): str(r["name"]) for r in roles if r.get("id") is not None}

    @app.get("/principals", response_class=HTMLResponse)
    async def principals_page(
        request: Request,
        staff: dict = Depends(staff_dep),
        session: AsyncSession = Depends(get_db),
    ):
        err = request.query_params.get("err")
        ok = request.query_params.get("ok")
        groups: list[dict] = []
        l2_rows: list[dict] = []
        detail: dict | None = None
        detail_chips: list[str] = []
        resource_count = None
        roles: list[dict] = []
        l2_pg_roles: list[dict] = []
        actor_kind = "l1"
        can_create = False
        can_create_l2 = False
        try:
            actor = await load_management_actor(session, staff)
        except PrincipalLifecycleError as exc:
            _raise_if_forbidden(exc)
            return render(
                request,
                "principals.html",
                {
                    "staff": staff,
                    "actor_kind": "none",
                    "groups": [],
                    "l2_rows": [],
                    "detail": None,
                    "detail_chips": [],
                    "resource_count": None,
                    "pg_roles": [],
                    "l2_pg_roles": [],
                    "can_create": False,
                    "can_create_l2": False,
                    "can_attach_web": False,
                    "can_attach_l2_telegram": False,
                    "can_detach_l2_telegram": False,
                    "flash_ok": ok,
                    "flash_err": exc.message,
                    "open_detail": False,
                },
            )

        owner = actor_is_owner(actor)
        actor_kind = "owner" if owner else "l1"
        names: dict[int, str] = {}
        try:
            # Owner env client is for Owner L1-create only — never L1 page loads.
            can_create = owner and owner_has_pg_admin_create_capability(staff)
            if can_create:
                roles = await _pg_roles_for_picker()
                names = _role_name_map(roles)
            # Owner creates L1 only — existing service DENY for Owner→L2.
            can_create_l2 = (not owner) and has_pg_admin_create_capability(staff)
            if can_create_l2:
                l2_pg_roles = await _l2_pg_roles_for_picker(session, staff)
                l2_names = _role_name_map(l2_pg_roles)
                if l2_names:
                    names.update(l2_names)
            l2_views = await list_level2_principals(session, staff)
            if public_views_contain_secret(l2_views):
                log.error("L2 list view leaked credential keys — refusing render")
                l2_views = []
                err = err or "نمایش فهرست نامعتبر است"
            l2_by_parent: dict[int, list[dict]] = {}
            for view in l2_views:
                item = _safe_public(view, hierarchy_label="سطح ۲")
                if not item.get("pg_role_name") and item.get("pg_role_id") is not None:
                    item["pg_role_name"] = names.get(int(item["pg_role_id"]))
                parent_key = int(item["parent_id"]) if item.get("parent_id") else 0
                l2_by_parent.setdefault(parent_key, []).append(item)
                l2_rows.append(item)

            if owner:
                l1_views = await list_level1_principals(session, staff)
                if public_views_contain_secret(l1_views):
                    log.error("principal list view leaked credential keys — refusing render")
                    l1_views = []
                    err = err or "نمایش فهرست نامعتبر است"
                for view in l1_views:
                    item = _safe_public(view, hierarchy_label="سطح ۱")
                    if not item.get("pg_role_name") and item.get("pg_role_id") is not None:
                        item["pg_role_name"] = names.get(int(item["pg_role_id"]))
                    kids = l2_by_parent.get(int(item["principal_id"]), [])
                    groups.append({"l1": item, "children": kids})
        except PrincipalLifecycleError as exc:
            _raise_if_forbidden(exc)
            err = exc.message
            roles = []
            l2_pg_roles = []
            can_create = False
            can_create_l2 = False
        except Exception:
            log.exception("principal list failed")
            err = "بارگذاری فهرست Principal ناموفق بود"
            roles = []
            l2_pg_roles = []
            can_create = False
            can_create_l2 = False

        detail_raw = (request.query_params.get("detail") or "").strip()
        if detail_raw.isdigit():
            try:
                target = await get_principal(session, int(detail_raw))
                if target is None:
                    raise PrincipalLifecycleError("Principal یافت نشد", code="not_found")
                if int(target.depth) == DEPTH_TWO:
                    view = await get_level2_principal_detail(
                        session, staff, int(detail_raw)
                    )
                    hierarchy = "سطح ۲"
                elif int(target.depth) == DEPTH_ONE and owner:
                    view = await get_level1_principal_detail(
                        session, staff, int(detail_raw)
                    )
                    hierarchy = "سطح ۱"
                else:
                    raise PrincipalLifecycleError(
                        "جزئیات Principal قابل نمایش نیست",
                        code="out_of_scope",
                    )
                if public_views_contain_secret(view):
                    err = err or "جزئیات Principal قابل نمایش نیست"
                else:
                    detail = _safe_public(view, hierarchy_label=hierarchy)
                    if not detail.get("pg_role_name") and detail.get("pg_role_id") is not None:
                        detail["pg_role_name"] = names.get(int(detail["pg_role_id"])) if names else None
                    if owner:
                        try:
                            from app.services.pasarguard import get_pg

                            chip_client: Any | None = get_pg()
                        except Exception:
                            chip_client = None
                    else:
                        chip_client = await _l1_pg_client(session, staff)
                    detail_chips = await _chips_for_role_id(
                        detail.get("pg_role_id"),
                        client=chip_client,
                    )
                    if int(target.depth) == DEPTH_ONE:
                        from app.services.principal_lifecycle import count_owned_resources

                        resource_count = await count_owned_resources(
                            session, int(view.principal_id)
                        )
            except PrincipalLifecycleError as exc:
                err = exc.message
            except Exception:
                log.exception("principal detail failed")
                err = err or "بارگذاری جزئیات ناموفق بود"

        page = render(
            request,
            "principals.html",
            {
                "staff": staff,
                "actor_kind": actor_kind,
                "groups": groups,
                "l2_rows": l2_rows,
                "detail": detail,
                "detail_chips": detail_chips,
                "resource_count": resource_count,
                "pg_roles": roles if can_create else [],
                "l2_pg_roles": l2_pg_roles if can_create_l2 else [],
                "can_create": can_create,
                "can_create_l2": can_create_l2,
                "can_attach_web": _can_attach_l2_web(detail),
                "can_attach_l2_telegram": _can_attach_l2_telegram(detail),
                "can_detach_l2_telegram": _can_detach_l2_telegram(detail),
                "flash_ok": ok,
                "flash_err": err,
                "open_detail": bool(detail),
            },
        )
        try:
            body = bytes(page.body).decode("utf-8", errors="ignore")
            if _html_contains_secret(body):
                log.error("principal page HTML contained secret markers — refusing")
                return RedirectResponse(
                    f"/principals?err={_q('نمایش صفحه نامعتبر است')}",
                    status_code=303,
                )
        except Exception:
            pass
        return page

    @app.post("/principals/{principal_id}/disable")
    async def principal_disable(
        principal_id: int,
        staff: dict = Depends(staff_dep),
        session: AsyncSession = Depends(get_db),
    ):
        try:
            await _disable_managed(session, staff, int(principal_id))
            await session.commit()
        except PrincipalLifecycleError as exc:
            _raise_if_forbidden(exc)
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q(exc.message)}",
                status_code=303,
            )
        except Exception:
            log.exception("principal disable failed")
            try:
                await session.rollback()
            except Exception:
                pass
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q('غیرفعال‌سازی ناموفق بود')}",
                status_code=303,
            )
        return RedirectResponse(
            f"/principals?detail={int(principal_id)}&ok={_q('Principal غیرفعال شد')}",
            status_code=303,
        )

    @app.post("/principals/{principal_id}/enable")
    async def principal_enable(
        principal_id: int,
        staff: dict = Depends(staff_dep),
        session: AsyncSession = Depends(get_db),
    ):
        try:
            await _enable_managed(session, staff, int(principal_id))
            await session.commit()
        except PrincipalLifecycleError as exc:
            _raise_if_forbidden(exc)
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q(exc.message)}",
                status_code=303,
            )
        except Exception:
            log.exception("principal enable failed")
            try:
                await session.rollback()
            except Exception:
                pass
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q('فعال‌سازی ناموفق بود')}",
                status_code=303,
            )
        return RedirectResponse(
            f"/principals?detail={int(principal_id)}&ok={_q('Principal فعال شد')}",
            status_code=303,
        )

    @app.post("/principals/create")
    async def principal_create(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        form = await request.form()
        # Hierarchy fields from the client are ignored even if posted.
        _ = form.get("parent_id")
        _ = form.get("depth")
        _ = form.get("org_principal_id")
        username = str(form.get("pg_username") or "").strip()
        password = str(form.get("pg_password") or "")
        note = str(form.get("note") or "").strip() or None
        role_raw = str(form.get("pg_role_id") or "").strip()
        role_id = int(role_raw) if role_raw.isdigit() else None
        key = f"ui-l1-{uuid.uuid4().hex}"
        try:
            result = await provision_level1_principal(
                session,
                staff,
                Level1ProvisionRequest(
                    pg_username=username,
                    pg_password=password,
                    idempotency_key=key,
                    pg_role_id=role_id,
                    note=note,
                ),
            )
            await session.commit()
        except PrincipalProvisionError as exc:
            return RedirectResponse(
                f"/principals?err={_q(exc.message)}",
                status_code=303,
            )
        except Exception:
            log.exception("principal create failed")
            try:
                await session.rollback()
            except Exception:
                pass
            return RedirectResponse(
                f"/principals?err={_q('ساخت Principal ناموفق بود')}",
                status_code=303,
            )
        created = "ساخته شد" if result.created else "از قبل موجود بود"
        return RedirectResponse(
            f"/principals?detail={int(result.principal.id)}"
            f"&ok={_q(f'Principal سطح ۱ {created}')}",
            status_code=303,
        )

    @app.post("/principals/create-l2")
    async def principal_create_l2(
        request: Request,
        staff: dict = Depends(staff_dep),
        session: AsyncSession = Depends(get_db),
    ):
        form = await request.form()
        # Client hierarchy / owner fields are ignored. Parent is always the
        # authenticated L1 inside provision_level2_child().
        posted_parent = form.get("parent_id")
        posted_depth = form.get("depth")
        _ = form.get("org_principal_id")
        _ = form.get("web_owner")
        _ = form.get("idempotency_key")
        username = str(form.get("pg_username") or "").strip()
        password = str(form.get("pg_password") or "")
        note = str(form.get("note") or "").strip() or None
        role_raw = str(form.get("pg_role_id") or "").strip()
        role_id = int(role_raw) if role_raw.isdigit() else None
        key = f"ui-l2-{uuid.uuid4().hex}"
        try:
            # Same actor gate as GET /principals: shop / L2 / sticky admin DENY.
            await load_management_actor(session, staff)
            result = await provision_level2_child(
                session,
                staff,
                Level2ProvisionRequest(
                    pg_username=username,
                    pg_password=password,
                    idempotency_key=key,
                    pg_role_id=role_id,
                    note=note,
                    parent_id=posted_parent,
                    depth=posted_depth,
                ),
            )
            await session.commit()
        except PrincipalLifecycleError as exc:
            _raise_if_forbidden(exc)
            return RedirectResponse(
                f"/principals?err={_q(exc.message)}",
                status_code=303,
            )
        except ChildProvisionError as exc:
            _raise_if_l2_create_denied(exc)
            return RedirectResponse(
                f"/principals?err={_q(exc.message)}",
                status_code=303,
            )
        except Exception:
            log.exception("l2 principal create failed")
            try:
                await session.rollback()
            except Exception:
                pass
            return RedirectResponse(
                f"/principals?err={_q('ساخت Principal سطح ۲ ناموفق بود')}",
                status_code=303,
            )
        created = "ساخته شد" if result.created else "از قبل موجود بود"
        return RedirectResponse(
            f"/principals?detail={int(result.principal.id)}"
            f"&ok={_q(f'Principal سطح ۲ {created}')}",
            status_code=303,
        )

    @app.post("/principals/{principal_id}/web-identity")
    async def principal_attach_l2_web(
        principal_id: int,
        request: Request,
        staff: dict = Depends(staff_dep),
        session: AsyncSession = Depends(get_db),
    ):
        form = await request.form()
        # Client hierarchy / identity fields are ignored. Target is the path id
        # after Product 2 scope checks; attach_level2_web_identity hashes the password.
        _ = form.get("principal_id")
        _ = form.get("parent_id")
        _ = form.get("depth")
        _ = form.get("org_principal_id")
        _ = form.get("role")
        _ = form.get("pg_username")
        _ = form.get("pg_password")
        username = str(form.get("username") or form.get("web_username") or "").strip()
        password = str(form.get("password") or form.get("web_password") or "")
        try:
            view = await get_level2_principal_detail(session, staff, int(principal_id))
            if not bool(view.can_manage):
                raise PrincipalLifecycleError(
                    "والد غیرفعال است — مدیریت فرزند مجاز نیست",
                    code="parent_disabled",
                )
            if str(view.status) != "active":
                raise PrincipalWebIdentityError(
                    "Principal غیرفعال است",
                    code="principal_disabled",
                )
            await attach_level2_web_identity(
                session,
                principal_id=int(principal_id),
                web_username=username,
                password=password,
            )
            await session.commit()
        except PrincipalLifecycleError as exc:
            _raise_if_web_attach_lifecycle_denied(exc)
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q(exc.message)}",
                status_code=303,
            )
        except PrincipalWebIdentityError as exc:
            _raise_if_web_attach_denied(exc)
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q(exc.message)}",
                status_code=303,
            )
        except Exception:
            log.exception("l2 web identity attach failed")
            try:
                await session.rollback()
            except Exception:
                pass
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q('فعال‌سازی ورود وب ناموفق بود')}",
                status_code=303,
            )
        return RedirectResponse(
            f"/principals?detail={int(principal_id)}"
            f"&ok={_q('ورود وب فعال شد')}",
            status_code=303,
        )

    def _bind_form_ignored(form) -> None:
        _ = form.get("principal_id")
        _ = form.get("parent_id")
        _ = form.get("depth")
        _ = form.get("org_principal_id")
        _ = form.get("web_owner")
        _ = form.get("bot_user_id")
        _ = form.get("role")

    @app.post("/principals/{principal_id}/telegram-bind")
    async def principal_bind_l2_telegram(
        principal_id: int,
        request: Request,
        staff: dict = Depends(staff_dep),
        session: AsyncSession = Depends(get_db),
    ):
        form = await request.form()
        _bind_form_ignored(form)
        raw = str(form.get("telegram_id") or "").strip()
        try:
            telegram_id = int(raw)
        except (TypeError, ValueError):
            telegram_id = 0
        try:
            await load_management_actor(session, staff)
            await bind_l2_bot_telegram(
                session,
                staff=staff,
                target_principal_id=int(principal_id),
                telegram_id=telegram_id,
            )
            await session.commit()
        except PrincipalLifecycleError as exc:
            _raise_if_forbidden(exc)
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q(exc.message)}",
                status_code=303,
            )
        except L2BotBindError as exc:
            _raise_if_l2_bind_denied(exc)
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q(exc.message)}",
                status_code=303,
            )
        except Exception:
            log.exception("l2 telegram bind failed")
            try:
                await session.rollback()
            except Exception:
                pass
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q('اتصال تلگرام ناموفق بود')}",
                status_code=303,
            )
        return RedirectResponse(
            f"/principals?detail={int(principal_id)}"
            f"&ok={_q('اتصال تلگرام انجام شد')}",
            status_code=303,
        )

    @app.post("/principals/{principal_id}/telegram-unbind")
    async def principal_unbind_l2_telegram(
        principal_id: int,
        request: Request,
        staff: dict = Depends(staff_dep),
        session: AsyncSession = Depends(get_db),
    ):
        form = await request.form()
        _bind_form_ignored(form)
        try:
            await load_management_actor(session, staff)
            await unbind_l2_bot_telegram(
                session,
                staff=staff,
                target_principal_id=int(principal_id),
            )
            await session.commit()
        except PrincipalLifecycleError as exc:
            _raise_if_forbidden(exc)
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q(exc.message)}",
                status_code=303,
            )
        except L2BotBindError as exc:
            _raise_if_l2_bind_denied(exc)
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q(exc.message)}",
                status_code=303,
            )
        except Exception:
            log.exception("l2 telegram unbind failed")
            try:
                await session.rollback()
            except Exception:
                pass
            return RedirectResponse(
                f"/principals?detail={int(principal_id)}&err={_q('قطع اتصال تلگرام ناموفق بود')}",
                status_code=303,
            )
        return RedirectResponse(
            f"/principals?detail={int(principal_id)}"
            f"&ok={_q('اتصال تلگرام قطع شد')}",
            status_code=303,
        )
