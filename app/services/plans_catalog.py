"""Sales-plan helpers shared by admin and reseller surfaces."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Plan
from app.services.pasarguard import as_list, get_pg


def catalog_owner_id(staff: dict | None) -> int | None:
    """Reseller bot_user_id for their catalog; None = platform (admin) catalog."""
    if not staff:
        return None
    if staff.get("role") == "reseller":
        rid = int(staff.get("bot_user_id") or 0)
        return rid or None
    return None


def apply_catalog_owner_filter(query, staff: dict | None):
    rid = catalog_owner_id(staff)
    if rid:
        return query.where(Plan.owner_reseller_id == rid)
    return query.where(Plan.owner_reseller_id.is_(None))


def plan_belongs_to_staff(plan: Plan | None, staff: dict | None) -> bool:
    if not plan:
        return False
    rid = catalog_owner_id(staff)
    if rid:
        return int(plan.owner_reseller_id or 0) == rid
    return plan.owner_reseller_id is None


def _allowed_id_set(raw) -> set[int] | None:
    """None = no restriction; empty set = nothing allowed."""
    if raw is None:
        return None
    try:
        return {int(x) for x in raw}
    except (TypeError, ValueError):
        return None


def filter_templates_for_staff(items: list[dict], staff: dict | None) -> list[dict]:
    if not staff or staff.get("role") == "admin":
        return items
    access = staff.get("pg_access") or {}
    allowed = _allowed_id_set(access.get("allowed_template_ids"))
    if allowed is None:
        return items
    if not allowed:
        return []
    return [t for t in items if int(t.get("id") or 0) in allowed]


def filter_groups_for_staff(items: list[dict], staff: dict | None) -> list[dict]:
    if not staff or staff.get("role") == "admin":
        return items
    access = staff.get("pg_access") or {}
    allowed = _allowed_id_set(access.get("allowed_group_ids"))
    if allowed is None:
        return items
    if not allowed:
        return []
    return [g for g in items if int(g.get("id") or 0) in allowed]


def template_allowed_for_staff(staff: dict | None, template_id: int | None) -> bool:
    if template_id is None:
        return False
    if not staff or staff.get("role") == "admin":
        return True
    access = staff.get("pg_access") or {}
    allowed = _allowed_id_set(access.get("allowed_template_ids"))
    if allowed is None:
        return True
    return int(template_id) in allowed


def groups_allowed_for_staff(staff: dict | None, group_ids: list[int]) -> bool:
    if not group_ids:
        return False
    if not staff or staff.get("role") == "admin":
        return True
    access = staff.get("pg_access") or {}
    allowed = _allowed_id_set(access.get("allowed_group_ids"))
    if allowed is None:
        return True
    return all(int(g) in allowed for g in group_ids)


def staff_can_create_pg_template(staff: dict | None) -> bool:
    if not staff or staff.get("role") == "admin":
        return True
    writes = staff.get("pg_writes") or {}
    return bool(writes.get("templates"))


async def load_pg_plan_options(staff: dict | None = None) -> tuple[list[dict], list[dict], str | None]:
    """Templates + groups for plan forms, filtered to staff PG access."""
    templates: list[dict] = []
    groups: list[dict] = []
    pg_error = None
    try:
        pg = get_pg()
        templates = await pg.get_user_templates_simple()
        full = await pg.get_user_templates()
        if isinstance(full, list) and full:
            templates = full
        else:
            templates = as_list(full, "templates") or templates
        groups = await pg.get_groups_simple()
    except Exception as e:
        pg_error = str(e)
    templates = [t for t in templates if isinstance(t, dict)]
    groups = [g for g in groups if isinstance(g, dict)]
    templates = filter_templates_for_staff(templates, staff)
    groups = filter_groups_for_staff(groups, staff)
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


async def get_owned_plan(
    session: AsyncSession,
    plan_id: int,
    staff: dict | None,
) -> Plan | None:
    plan = await session.get(Plan, plan_id)
    if not plan_belongs_to_staff(plan, staff):
        return None
    return plan


def parse_group_ids_from_form(form: Any) -> list[int]:
    ids: list[int] = []
    for k, v in form.items():
        if str(k).startswith("group_") and str(v).isdigit():
            ids.append(int(v))
    return ids
