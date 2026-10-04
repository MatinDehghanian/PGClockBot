"""Shop-scoped plan categories — fail-closed like the sales-plan catalog."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Plan, PlanCategory
from app.services.plans_catalog import (
    apply_catalog_owner_filter,
    catalog_owner_id,
    require_catalog_owner_id,
)
from app.services.shop_scope import ShopScopeError, is_platform_admin, shop_owner_id


def apply_category_owner_filter(query, staff: dict | None):
    """Filter categories to the staff shop. Non-admin without scope → empty."""
    if is_platform_admin(staff):
        return query.where(PlanCategory.owner_reseller_id.is_(None))
    if not staff:
        return query.where(PlanCategory.owner_reseller_id.is_(None))
    rid = shop_owner_id(staff)
    if not rid:
        return query.where(PlanCategory.id < 0)
    return query.where(PlanCategory.owner_reseller_id == rid)


def category_belongs_to_staff(cat: PlanCategory | None, staff: dict | None) -> bool:
    if not cat:
        return False
    if is_platform_admin(staff):
        return cat.owner_reseller_id is None
    if not staff:
        return cat.owner_reseller_id is None
    rid = shop_owner_id(staff)
    if not rid:
        return False
    return int(cat.owner_reseller_id or 0) == int(rid)


def category_matches_shop(cat: PlanCategory | None, shop_rid: int | None) -> bool:
    """Bot/runtime check: category must belong to the current shop context."""
    if not cat or not cat.is_active:
        return False
    if shop_rid:
        return int(cat.owner_reseller_id or 0) == int(shop_rid)
    return cat.owner_reseller_id is None


async def list_categories(
    session: AsyncSession,
    staff: dict | None,
    *,
    active_only: bool = False,
) -> list[PlanCategory]:
    q = select(PlanCategory).order_by(PlanCategory.sort_order, PlanCategory.id)
    q = apply_category_owner_filter(q, staff)
    if active_only:
        q = q.where(PlanCategory.is_active.is_(True))
    return list((await session.execute(q)).scalars().all())


async def list_shop_categories(
    session: AsyncSession,
    *,
    reseller_id: int | None = None,
    active_only: bool = True,
) -> list[PlanCategory]:
    """Bot catalog listing by shop context (not staff)."""
    from app.services.users import current_shop_reseller_id

    rid = reseller_id if reseller_id is not None else current_shop_reseller_id()
    q = select(PlanCategory).order_by(PlanCategory.sort_order, PlanCategory.id)
    if rid:
        q = q.where(PlanCategory.owner_reseller_id == int(rid))
    else:
        q = q.where(PlanCategory.owner_reseller_id.is_(None))
    if active_only:
        q = q.where(PlanCategory.is_active.is_(True))
    return list((await session.execute(q)).scalars().all())


async def get_owned_category(
    session: AsyncSession, category_id: int, staff: dict | None
) -> PlanCategory | None:
    cat = await session.get(PlanCategory, int(category_id))
    if not category_belongs_to_staff(cat, staff):
        return None
    return cat


async def create_category(
    session: AsyncSession,
    staff: dict | None,
    *,
    name: str,
    description: str | None = None,
    sort_order: int = 0,
) -> PlanCategory:
    owner_id = require_catalog_owner_id(staff)
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("نام دسته‌بندی الزامی است")
    if len(cleaned) > 128:
        raise ValueError("نام دسته‌بندی خیلی طولانی است")
    desc = (description or "").strip() or None
    if desc and len(desc) > 255:
        raise ValueError("توضیح خیلی طولانی است")
    cat = PlanCategory(
        name=cleaned,
        description=desc,
        owner_reseller_id=owner_id,
        sort_order=int(sort_order or 0),
        is_active=True,
    )
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return cat


async def update_category(
    session: AsyncSession,
    staff: dict | None,
    category_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
) -> PlanCategory:
    cat = await get_owned_category(session, category_id, staff)
    if not cat:
        raise ShopScopeError("دسته‌بندی یافت نشد")
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("نام دسته‌بندی الزامی است")
        if len(cleaned) > 128:
            raise ValueError("نام دسته‌بندی خیلی طولانی است")
        cat.name = cleaned
    if description is not None:
        desc = description.strip() or None
        if desc and len(desc) > 255:
            raise ValueError("توضیح خیلی طولانی است")
        cat.description = desc
    if sort_order is not None:
        cat.sort_order = int(sort_order)
    if is_active is not None:
        cat.is_active = bool(is_active)
    await session.commit()
    await session.refresh(cat)
    return cat


async def delete_category(
    session: AsyncSession, staff: dict | None, category_id: int
) -> None:
    cat = await get_owned_category(session, category_id, staff)
    if not cat:
        raise ShopScopeError("دسته‌بندی یافت نشد")
    # Detach plans in this shop only (defense-in-depth on owner_reseller_id).
    detach = (
        update(Plan)
        .where(Plan.category_id == int(category_id))
        .values(category_id=None)
        .execution_options(synchronize_session=False)
    )
    if cat.owner_reseller_id is None:
        detach = detach.where(Plan.owner_reseller_id.is_(None))
    else:
        detach = detach.where(Plan.owner_reseller_id == int(cat.owner_reseller_id))
    await session.execute(detach)
    await session.delete(cat)
    await session.commit()


async def resolve_category_for_plan_write(
    session: AsyncSession,
    staff: dict | None,
    category_id_raw: str | int | None,
    *,
    allow_inactive_id: int | None = None,
) -> int | None:
    """Parse optional category id; must belong to the same shop as the plan.

    ``allow_inactive_id`` lets plan edit keep the currently assigned inactive
    category without forcing a clear/reassign.
    """
    if category_id_raw is None:
        return None
    raw = str(category_id_raw).strip()
    if not raw:
        return None
    try:
        cid = int(raw)
    except (TypeError, ValueError) as e:
        raise ValueError("دسته‌بندی نامعتبر است") from e
    cat = await get_owned_category(session, cid, staff)
    if not cat:
        raise ShopScopeError("دسته‌بندی در این فروشگاه یافت نشد")
    if not cat.is_active:
        if allow_inactive_id is not None and int(cat.id) == int(allow_inactive_id):
            return int(cat.id)
        raise ValueError("این دسته‌بندی غیرفعال است")
    return int(cat.id)


async def category_map_for_plans(
    session: AsyncSession, staff: dict | None, plans: list[Plan]
) -> dict[int, PlanCategory]:
    ids = {int(p.category_id) for p in plans if p.category_id}
    if not ids:
        return {}
    q = select(PlanCategory).where(PlanCategory.id.in_(ids))
    q = apply_category_owner_filter(q, staff)
    rows = list((await session.execute(q)).scalars().all())
    return {int(c.id): c for c in rows}


def staff_shop_key(staff: dict | None) -> str:
    """Stable key for tests / logging."""
    rid = catalog_owner_id(staff)
    return "platform" if rid is None else f"shop:{rid}"
