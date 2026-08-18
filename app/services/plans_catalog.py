"""Sales-plan helpers shared by admin and reseller surfaces."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Plan
from app.services.pasarguard import as_list, get_pg
from app.services.pg_quota import PgQuotaError, assert_user_plan_within_limits
from app.services.shop_scope import ShopScopeError, is_platform_admin, shop_owner_id

log = logging.getLogger(__name__)
def catalog_owner_id(staff: dict | None) -> int | None:
    """Reseller bot_user_id for their catalog; None = platform (admin) catalog only.

    Non-admin without a shop id returns None; callers must use
    ``apply_catalog_owner_filter`` / ``require_catalog_owner_id`` which fail
    closed for that case (never treat as platform).
    """
    if not staff:
        return None
    if is_platform_admin(staff):
        return None
    return shop_owner_id(staff)


def require_catalog_owner_id(staff: dict | None) -> int | None:
    """Owner id for catalog writes: admin → None (platform); reseller → positive id.

    Raises ShopScopeError for any non-admin without a shop scope so they cannot
    create/edit platform plans or settings.
    """
    if is_platform_admin(staff):
        return None
    rid = shop_owner_id(staff)
    if not rid:
        raise ShopScopeError(
            "حساب شما به فروشگاه متصل نیست — دسترسی به کاتالوگ ادمین اصلی مجاز نیست"
        )
    return rid


def apply_catalog_owner_filter(query, staff: dict | None):
    """Filter plans to the staff shop. Non-admin without scope → empty result."""
    if is_platform_admin(staff):
        return query.where(Plan.owner_reseller_id.is_(None))
    if not staff:
        # Unauthenticated/internal callers: platform catalog only
        return query.where(Plan.owner_reseller_id.is_(None))
    rid = shop_owner_id(staff)
    if not rid:
        # Fail closed: never show platform catalog to secondary staff
        return query.where(Plan.id < 0)
    return query.where(Plan.owner_reseller_id == rid)


def plan_belongs_to_staff(plan: Plan | None, staff: dict | None) -> bool:
    if not plan:
        return False
    if is_platform_admin(staff):
        return plan.owner_reseller_id is None
    if not staff:
        return plan.owner_reseller_id is None
    rid = shop_owner_id(staff)
    if not rid:
        return False
    return int(plan.owner_reseller_id or 0) == rid


def _admin_pg_unrestricted(staff: dict | None) -> bool:
    """True for a genuine platform Owner whose env PasarGuard account has no
    group/template restriction.

    ``role == "admin"`` alone is not enough: a Hybrid Owner setup may point
    the platform ``.env`` PG credentials at a *limited* PasarGuard admin
    (``pg_is_owner`` is explicitly ``False`` in that case, set by
    ``pg_access.enrich_platform_admin_staff``). Such an account must go
    through the exact same ``allowed_group_ids`` / ``allowed_template_ids``
    filtering as any other role — otherwise a platform admin's own
    PasarGuard-side group restriction (e.g. only groups 1 and 2) would be
    silently ignored in the web panel. Missing key (unenriched / legacy
    staff dict, or non-Hybrid single-owner deployments) defaults to True to
    preserve prior behavior.
    """
    if not staff or staff.get("role") != "admin":
        return False
    return bool(staff.get("pg_is_owner", True))


def _allowed_id_set(raw) -> set[int] | None:
    """Parse allow-list.

    ``None`` input → None (unresolved — callers must not treat as unrestricted
    for non-Owner mutations). Invalid payloads → empty set (deny everything).
    """
    if raw is None:
        return None
    try:
        return {int(x) for x in raw}
    except (TypeError, ValueError):
        return set()


def filter_templates_for_staff(
    items: list[dict],
    staff: dict | None,
    *,
    trust_client_scope: bool | None = None,
) -> list[dict]:
    """Filter templates for restricted staff.

    When ``allowed_template_ids`` is None:
    - trust_client_scope True (reseller own-token lists) → keep items
    - trust_client_scope False → fail closed ``[]`` (no unrestricted owner lists)
    """
    if not staff or _admin_pg_unrestricted(staff):
        return items
    if trust_client_scope is None:
        from app.services.pg_read import trust_pg_list_scope

        trust_client_scope = trust_pg_list_scope(staff)
    access = staff.get("pg_access") or {}
    allowed = _allowed_id_set(access.get("allowed_template_ids"))
    if allowed is None:
        return items if trust_client_scope else []
    if not allowed:
        return []
    return [t for t in items if int(t.get("id") or 0) in allowed]


def filter_groups_for_staff(
    items: list[dict],
    staff: dict | None,
    *,
    trust_client_scope: bool | None = None,
) -> list[dict]:
    if not staff or _admin_pg_unrestricted(staff):
        return items
    if trust_client_scope is None:
        from app.services.pg_read import trust_pg_list_scope

        trust_client_scope = trust_pg_list_scope(staff)
    access = staff.get("pg_access") or {}
    allowed = _allowed_id_set(access.get("allowed_group_ids"))
    if allowed is None:
        return items if trust_client_scope else []
    if not allowed:
        return []
    return [g for g in items if int(g.get("id") or 0) in allowed]


def template_allowed_for_staff(staff: dict | None, template_id: int | None) -> bool:
    """Mutation/object check. Missing allow-list is NOT unrestricted for non-Owner (M1)."""
    if template_id is None:
        return False
    if not staff or _admin_pg_unrestricted(staff):
        return True
    access = staff.get("pg_access") or {}
    allowed = _allowed_id_set(access.get("allowed_template_ids"))
    if allowed is None:
        # Unresolved allow-list ≠ unrestricted. Hybrid limited admin → deny.
        # Reseller / credentialed pg_staff → own-client scopes the ID space.
        from app.services.pg_read import staff_pg_credentials_ready
        from app.services.shop_scope import is_platform_admin

        if is_platform_admin(staff):
            return False
        return bool(staff_pg_credentials_ready(staff))
    if not allowed:
        return False
    return int(template_id) in allowed


def groups_allowed_for_staff(staff: dict | None, group_ids: list[int]) -> bool:
    """Mutation/object check. Missing allow-list is NOT unrestricted for non-Owner (M1)."""
    if not group_ids:
        return False
    if not staff or _admin_pg_unrestricted(staff):
        return True
    access = staff.get("pg_access") or {}
    allowed = _allowed_id_set(access.get("allowed_group_ids"))
    if allowed is None:
        from app.services.pg_read import staff_pg_credentials_ready
        from app.services.shop_scope import is_platform_admin

        if is_platform_admin(staff):
            return False
        return bool(staff_pg_credentials_ready(staff))
    if not allowed:
        return False
    return all(int(g) in allowed for g in group_ids)


def staff_can_create_pg_template(staff: dict | None) -> bool:
    """True only when the principal may perform templates.create (exact ACL)."""
    if not staff:
        return False
    from app.services.pg_access import staff_pg_action

    # Hybrid: platform admin also needs templates.create on the env PG role.
    return staff_pg_action(staff, "templates", "create")


async def load_pg_plan_options(
    staff: dict | None = None,
    *,
    session=None,
) -> tuple[list[dict], list[dict], str | None]:
    """Templates + groups for plan forms, filtered to staff PG access.

    Uses tenant-safe read client (C1). Restricted staff without own credentials
    get empty lists (no owner-token fetch).
    """
    templates: list[dict] = []
    groups: list[dict] = []
    pg_error = None
    try:
        from app.services.pg_read import PgReadDenied, staff_pg_read_client, trust_pg_list_scope

        if staff and staff.get("role") != "admin":
            try:
                pg = await staff_pg_read_client(session, staff)
            except PgReadDenied as e:
                return [], [], e.message
        else:
            pg = get_pg()
        try:
            await pg.ensure_token()
        except Exception as e:
            log.warning("load_pg_plan_options token failed: %s", e)
            return [], [], "اتصال به پاسارگارد برقرار نشد"
        try:
            templates = await pg.get_user_templates_simple()
            full = await pg.get_user_templates()
            if isinstance(full, list) and full:
                templates = full
            else:
                templates = as_list(full, "templates") or templates
        except Exception as e:
            log.warning("load_pg_plan_options templates unavailable: %s", e)
            templates = []
        try:
            groups = await pg.get_groups_simple()
        except Exception as e:
            log.warning("load_pg_plan_options groups unavailable: %s", e)
            groups = []
    except Exception as e:
        # Never surface raw PG/HTTP exception text to the panel (info leak).
        log.warning("load_pg_plan_options failed: %s", e)
        pg_error = "اتصال به پاسارگارد برقرار نشد"
    templates = [t for t in templates if isinstance(t, dict)]
    groups = [g for g in groups if isinstance(g, dict)]
    trust = trust_pg_list_scope(staff) if staff else True
    templates = filter_templates_for_staff(templates, staff, trust_client_scope=trust)
    groups = filter_groups_for_staff(groups, staff, trust_client_scope=trust)
    return templates, groups, pg_error


async def list_catalog_plans(
    session: AsyncSession,
    staff: dict | None,
    *,
    include_trial: bool = True,
) -> list[Plan]:
    q = apply_catalog_owner_filter(select(Plan), staff).order_by(Plan.sort_order, Plan.id)
    plans = list((await session.execute(q)).scalars().all())
    if not include_trial:
        plans = [p for p in plans if not p.is_trial]
    return plans


async def plan_limit_issue(staff: dict | None, plan: Plan | None) -> str | None:
    """Return a human message when a saved user-facing plan exceeds live PG limits."""
    if not plan or not staff:
        return None
    try:
        data_limit = (
            int(float(plan.data_limit_gb) * (1024**3))
            if plan.data_limit_gb is not None
            else None
        )
    except (TypeError, ValueError):
        return "حجم پلن نامعتبر است"
    try:
        await assert_user_plan_within_limits(
            staff,
            data_limit=data_limit,
            duration_days=int(plan.duration_days or 0),
            label="پلن",
        )
    except PgQuotaError as exc:
        return exc.message
    if plan.pg_template_id and not template_allowed_for_staff(staff, int(plan.pg_template_id)):
        return "تمپلیت انتخاب‌شده دیگر در دسترس این حساب نیست"
    if plan.pg_group_ids:
        try:
            gids = [
                int(x.strip()) for x in str(plan.pg_group_ids).split(",") if x.strip()
            ]
        except (TypeError, ValueError):
            return "گروه‌های پلن نامعتبر است"
        if gids and not groups_allowed_for_staff(staff, gids):
            return "یکی از گروه‌های این پلن دیگر در دسترس این حساب نیست"
    return None


def custom_range_limit_issue(
    *,
    min_gb: float,
    max_gb: float,
    min_days: int,
    max_days: int,
    snapshot: dict[str, Any] | None,
) -> str | None:
    """Pure UI hint from a preloaded quota snapshot for custom-plan settings."""
    snap = snapshot or {}
    if not snap.get("restricted"):
        return None
    data_max = snap.get("per_user_data_max")
    if data_max is not None and data_max > 0:
        try:
            if int(float(max_gb) * (1024**3)) > int(data_max):
                from app.services.formatting import format_bytes

                return f"حداکثر حجم پلن دلخواه نمی‌تواند بیشتر از {format_bytes(data_max)} باشد"
        except (TypeError, ValueError):
            return "حداکثر حجم پلن دلخواه نامعتبر است"
    expire_max = snap.get("per_user_expire_max")
    if expire_max is not None and expire_max > 0:
        now = datetime.now(timezone.utc).timestamp()
        seconds = int(max_days or 0) * 86400
        if seconds <= 0:
            return "حداکثر مدت پلن دلخواه باید مشخص باشد"
        if now + seconds - now > int(expire_max):
            days = max(1, int(int(expire_max) / 86400))
            return f"حداکثر مدت پلن دلخواه نمی‌تواند بیشتر از {days} روز باشد"
    return None


async def get_owned_plan(
    session: AsyncSession,
    plan_id: int,
    staff: dict | None,
) -> Plan | None:
    plan = await session.get(Plan, plan_id)
    if not plan_belongs_to_staff(plan, staff):
        return None
    return plan


def parse_group_ids_from_form(form: Any, *, prefix: str = "group_") -> list[int]:
    ids: list[int] = []
    for k, v in form.items():
        if str(k).startswith(prefix) and str(v).isdigit():
            ids.append(int(v))
    return ids
