"""Cascading volume budgets for L1 → L2 (and sub-admin → reseller).

Rule: for any account with a finite ceiling, local allocation + external
allocation + sum of ceilings granted to direct children ≤ own ceiling.

Children without a stored ceiling stay unlimited for their own selling but
count as zero toward the parent (same zero-count rule as unlimited services)
and are listed as warnings on the parent's capacity page.

A parent/sub-admin without a ceiling applies no cascade limit.
Lock order is always parent shop row → child shop row.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    OrgPrincipal,
    OrgPrincipalProvision,
    PgAdminSubscription,
    ResellerProfile,
)
from app.services.billing import GB
from app.services.org_principals import DEPTH_ONE, DEPTH_TWO, STATUS_ACTIVE
from app.services.volume_allocation import (
    VolumeAllocationError,
    ceiling_bytes_for_profile,
    lock_reseller_profile,
    sum_allocated_bytes,
)

logger = logging.getLogger(__name__)


class CascadeBudgetError(VolumeAllocationError):
    """Parent/child cascade budget rejection."""


async def provision_row_for_principal(
    session: AsyncSession, principal_id: int
) -> OrgPrincipalProvision | None:
    return await session.scalar(
        select(OrgPrincipalProvision)
        .where(OrgPrincipalProvision.principal_id == int(principal_id))
        .order_by(OrgPrincipalProvision.id.desc())
        .limit(1)
    )


def ceiling_gb_from_provision(row: OrgPrincipalProvision | None) -> int | None:
    """Finite ceiling in GB, or None when unlimited / unset."""
    if row is None:
        return None
    raw = getattr(row, "volume_ceiling_gb", None)
    if raw is None:
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


async def shop_id_for_principal(
    session: AsyncSession, principal: OrgPrincipal
) -> int | None:
    rid = getattr(principal, "reseller_profile_id", None)
    if rid is None:
        return None
    profile = await session.get(ResellerProfile, int(rid))
    if profile is None:
        return None
    return int(profile.user_id)


async def list_direct_child_principals(
    session: AsyncSession, parent_id: int
) -> list[OrgPrincipal]:
    return list(
        (
            await session.execute(
                select(OrgPrincipal).where(
                    OrgPrincipal.parent_id == int(parent_id),
                    OrgPrincipal.status == STATUS_ACTIVE,
                )
            )
        ).scalars().all()
    )


async def sum_children_ceiling_bytes(
    session: AsyncSession, parent_principal_id: int
) -> tuple[int, list[dict[str, Any]]]:
    """Sum finite ceilings granted to direct children; list unlimited children."""
    children = await list_direct_child_principals(session, parent_principal_id)
    if not children:
        return 0, []
    child_ids = [int(c.id) for c in children]
    rows = (
        await session.execute(
            select(OrgPrincipalProvision).where(
                OrgPrincipalProvision.principal_id.in_(child_ids)
            )
        )
    ).scalars().all()
    # Latest provision per principal
    by_pid: dict[int, OrgPrincipalProvision] = {}
    for row in rows:
        pid = int(row.principal_id)
        prev = by_pid.get(pid)
        if prev is None or int(row.id) > int(prev.id):
            by_pid[pid] = row
    total = 0
    unlimited: list[dict[str, Any]] = []
    for child in children:
        gb = ceiling_gb_from_provision(by_pid.get(int(child.id)))
        if gb is None:
            unlimited.append(
                {
                    "principal_id": int(child.id),
                    "pg_username": str(child.pg_username or ""),
                }
            )
            continue
        total += int(gb) * int(GB)
    return int(total), unlimited


async def parent_effective_allocated_bytes(
    session: AsyncSession, *, shop_id: int, principal_id: int
) -> int:
    """Shop allocation (local+external) plus ceilings granted to children."""
    base = await sum_allocated_bytes(session, int(shop_id))
    children_bytes, _ = await sum_children_ceiling_bytes(session, int(principal_id))
    return int(base) + int(children_bytes)


async def assert_parent_can_grant_child_ceiling(
    session: AsyncSession,
    *,
    parent_shop_id: int,
    parent_principal_id: int,
    child_principal_id: int | None,
    new_ceiling_gb: int,
    previous_ceiling_gb: int | None,
) -> None:
    """Positive delta on a child ceiling must fit the parent's remaining budget.

    If the parent has no finite ceiling, cascade is skipped (document this for
    sub-admins without a ceiling).
    """
    parent_profile = await lock_reseller_profile(session, int(parent_shop_id))
    if parent_profile is None:
        return
    parent_ceiling = await ceiling_bytes_for_profile(session, parent_profile)
    if parent_ceiling is None:
        # Parent unlimited / unknown → no cascade limit (sub-admin without ceiling).
        return

    try:
        new_gb = int(new_ceiling_gb)
    except (TypeError, ValueError) as exc:
        raise CascadeBudgetError("سقف حجم فرزند نامعتبر است") from exc
    if new_gb <= 0:
        raise CascadeBudgetError("سقف حجم فرزند باید مثبت باشد")

    prev = int(previous_ceiling_gb) if previous_ceiling_gb and previous_ceiling_gb > 0 else 0
    delta = (new_gb - prev) * int(GB)
    if delta <= 0:
        return

    used = await parent_effective_allocated_bytes(
        session, shop_id=int(parent_shop_id), principal_id=int(parent_principal_id)
    )
    # When raising an existing child, the previous ceiling is already inside ``used``.
    if used + delta > parent_ceiling:
        from app.services.formatting import format_bytes

        raise CascadeBudgetError(
            f"سقف حجم پر است: {format_bytes(used)} از {format_bytes(parent_ceiling)}"
        )


async def assert_child_ceiling_above_own_allocation(
    session: AsyncSession,
    *,
    child_shop_id: int | None,
    new_ceiling_gb: int,
) -> None:
    """Refuse lowering a child ceiling below what the child has already allocated."""
    if child_shop_id is None:
        return
    allocated = await sum_allocated_bytes(session, int(child_shop_id))
    new_bytes = int(new_ceiling_gb) * int(GB)
    if allocated > new_bytes:
        from app.services.formatting import format_bytes

        raise CascadeBudgetError(
            f"کاهش سقف فرزند به زیر تخصیص فعلی مجاز نیست "
            f"({format_bytes(allocated)} تخصیص‌یافته؛ سقف پیشنهادی {format_bytes(new_bytes)})"
        )


async def set_child_volume_ceiling(
    session: AsyncSession,
    *,
    parent_principal: OrgPrincipal,
    child_principal: OrgPrincipal,
    ceiling_gb: int,
    actor_principal_id: int,
) -> OrgPrincipalProvision:
    """Set or raise/lower a child's cascade ceiling with parent→child locks."""
    if int(child_principal.parent_id or 0) != int(parent_principal.id):
        raise CascadeBudgetError("این فرزند متعلق به این والد نیست")
    if int(actor_principal_id) == int(child_principal.id):
        raise CascadeBudgetError("نماینده نمی‌تواند سقف خودش را تغییر دهد")
    from app.services.org_principals import is_owner_principal

    actor = await session.get(OrgPrincipal, int(actor_principal_id))
    is_parent = int(actor_principal_id) == int(parent_principal.id)
    is_owner = actor is not None and is_owner_principal(actor)
    if not is_parent and not is_owner:
        raise CascadeBudgetError("تغییر سقف فرزند فقط توسط والد یا مالک مجاز است")

    parent_shop = await shop_id_for_principal(session, parent_principal)
    child_shop = await shop_id_for_principal(session, child_principal)
    if parent_shop is None:
        raise CascadeBudgetError("فروشگاه والد یافت نشد")

    # Deadlock-safe: always parent then child.
    await lock_reseller_profile(session, int(parent_shop))
    if child_shop is not None:
        await lock_reseller_profile(session, int(child_shop))

    prov = await provision_row_for_principal(session, int(child_principal.id))
    if prov is None:
        raise CascadeBudgetError("سابقه تخصیص فرزند یافت نشد")
    prev = ceiling_gb_from_provision(prov)
    await assert_child_ceiling_above_own_allocation(
        session, child_shop_id=child_shop, new_ceiling_gb=int(ceiling_gb)
    )
    await assert_parent_can_grant_child_ceiling(
        session,
        parent_shop_id=int(parent_shop),
        parent_principal_id=int(parent_principal.id),
        child_principal_id=int(child_principal.id),
        new_ceiling_gb=int(ceiling_gb),
        previous_ceiling_gb=prev,
    )
    prov.volume_ceiling_gb = int(ceiling_gb)
    await session.flush()

    # Keep the child's subscription clock aligned with the cascade ceiling.
    if child_shop is not None:
        child_profile = await session.scalar(
            select(ResellerProfile).where(ResellerProfile.user_id == int(child_shop))
        )
        if child_profile and child_profile.pg_admin_username:
            sub = await session.scalar(
                select(PgAdminSubscription).where(
                    PgAdminSubscription.pg_username == child_profile.pg_admin_username
                )
            )
            if sub is not None:
                sub.base_gb = int(ceiling_gb)
                # Preserve extras relative to a raised base: extras stay; when lowering,
                # extras that would exceed are left for operator review (base is SoT).
            else:
                session.add(
                    PgAdminSubscription(
                        pg_username=child_profile.pg_admin_username,
                        base_gb=int(ceiling_gb),
                        base_users=0,
                    )
                )
            await session.flush()
    return prov


async def assert_l2_extra_gb_against_parent(
    session: AsyncSession,
    *,
    child_profile: ResellerProfile,
    add_gb: int,
) -> None:
    """When an L2 buys extra GB, re-check the L1 parent's cascade budget."""
    principal = await session.scalar(
        select(OrgPrincipal).where(
            OrgPrincipal.reseller_profile_id == int(child_profile.id)
        )
    )
    if principal is None or int(principal.depth) != DEPTH_TWO:
        return
    parent = await session.get(OrgPrincipal, int(principal.parent_id or 0))
    if parent is None:
        return
    parent_shop = await shop_id_for_principal(session, parent)
    if parent_shop is None:
        return
    prov = await provision_row_for_principal(session, int(principal.id))
    prev = ceiling_gb_from_provision(prov)
    # Buying extra raises the child's effective ceiling.
    current_total_gb = prev or 0
    if prev is None:
        # Unlimited child: still consume parent budget for the purchased extras.
        current_total_gb = 0
        uname = (child_profile.pg_admin_username or "").strip()
        if uname:
            sub = await session.scalar(
                select(PgAdminSubscription).where(PgAdminSubscription.pg_username == uname)
            )
            if sub is not None:
                current_total_gb = int(sub.base_gb or 0) + int(sub.extra_gb_purchased or 0)
    new_total = int(current_total_gb) + int(add_gb)
    await lock_reseller_profile(session, int(parent_shop))
    await lock_reseller_profile(session, int(child_profile.user_id))
    await assert_parent_can_grant_child_ceiling(
        session,
        parent_shop_id=int(parent_shop),
        parent_principal_id=int(parent.id),
        child_principal_id=int(principal.id),
        new_ceiling_gb=new_total,
        previous_ceiling_gb=current_total_gb if current_total_gb > 0 else None,
    )
    if prov is not None:
        prov.volume_ceiling_gb = int(new_total)
        await session.flush()


async def cascade_warn_items_for_parent(
    session: AsyncSession, parent_principal_id: int
) -> list[dict[str, Any]]:
    """Children without a cascade ceiling (count as zero toward parent)."""
    _total, unlimited = await sum_children_ceiling_bytes(session, parent_principal_id)
    return unlimited


async def include_children_in_gate(
    session: AsyncSession,
    *,
    shop_id: int,
    delta_bytes: int,
    audience: str = "admin",
) -> None:
    """Extend the shop gate with children ceilings when the shop is an L1 parent."""
    profile = await session.scalar(
        select(ResellerProfile).where(ResellerProfile.user_id == int(shop_id))
    )
    if profile is None:
        return
    principal = await session.scalar(
        select(OrgPrincipal).where(
            OrgPrincipal.reseller_profile_id == int(profile.id),
            OrgPrincipal.depth == DEPTH_ONE,
            OrgPrincipal.status == STATUS_ACTIVE,
        )
    )
    if principal is None:
        return
    ceiling = await ceiling_bytes_for_profile(session, profile)
    if ceiling is None:
        return
    children_bytes, _ = await sum_children_ceiling_bytes(session, int(principal.id))
    if children_bytes <= 0:
        return
    # Local+external already checked by caller against ceiling; re-check with children.
    from app.services.volume_allocation import (
        CUSTOMER_UNAVAILABLE_MSG,
        sum_local_allocated_bytes,
    )

    local = await sum_local_allocated_bytes(session, int(shop_id))
    external = int(getattr(profile, "external_allocated_bytes", 0) or 0)
    if local + external + children_bytes + max(0, int(delta_bytes)) > ceiling:
        from app.services.formatting import format_bytes

        used = local + external + children_bytes
        msg = (
            CUSTOMER_UNAVAILABLE_MSG
            if audience == "customer"
            else f"سقف حجم پر است: {format_bytes(used)} از {format_bytes(ceiling)}"
        )
        raise VolumeAllocationError(msg, for_customer=(audience == "customer"))
