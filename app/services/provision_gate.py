"""Shared Provision Gate: PG quota + Billing empty-balance + volume allocation.

Every operation that creates a new financial commitment for a reseller shop
must pass through here (create user, renew, volume/plan change, similar).
Volume rules live in ``volume_allocation``; this module only calls them.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.billing import BillingError, assert_billing_allows_provision
from app.services.pg_quota import (
    PgQuotaError,
    assert_can_create_user,
    assert_can_modify_user,
    assert_can_mutate_owned_users,
    assert_reseller_can_deliver,
    assert_reseller_can_renew,
)
from app.services.shop_scope import shop_owner_id
from app.services.volume_allocation import VolumeAllocationError, assert_volume_delta_allowed


class ProvisionError(Exception):
    """Unified provision failure (quota, billing, or volume allocation)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _wrap(exc: Exception) -> ProvisionError:
    if isinstance(exc, VolumeAllocationError):
        return ProvisionError(exc.user_message())
    if isinstance(exc, (PgQuotaError, BillingError, ProvisionError)):
        return ProvisionError(getattr(exc, "message", str(exc)))
    return ProvisionError(str(exc))


async def _assert_volume_for_create(
    session: AsyncSession,
    *,
    reseller_user_id: int | None,
    data_limit: int | None,
    quantity: int,
    audience: str = "admin",
) -> None:
    if reseller_user_id is None:
        return
    qty = max(1, int(quantity or 1))
    if data_limit is None:
        # Template / unknown intended limit — fail closed when the gate applies.
        await assert_volume_delta_allowed(
            session,
            shop_id=int(reseller_user_id),
            delta_bytes=None,
            audience=audience,  # type: ignore[arg-type]
        )
        return
    try:
        per_user = int(data_limit)
    except (TypeError, ValueError) as exc:
        raise VolumeAllocationError(
            "سقف حجم این نماینده مشخص نیست",
            for_customer=(audience == "customer"),
        ) from exc
    # Unlimited create (0) is rejected inside assert_volume_delta_allowed.
    await assert_volume_delta_allowed(
        session,
        shop_id=int(reseller_user_id),
        delta_bytes=per_user * qty if per_user > 0 else 0,
        audience=audience,  # type: ignore[arg-type]
        allow_unlimited=(per_user > 0),
    )


def reseller_id_from_staff(staff: dict | None) -> int | None:
    """Billing applies to reseller shop owners (not platform admin / bare pg_staff)."""
    return shop_owner_id(staff)


async def assert_provision_create(
    session: AsyncSession,
    *,
    staff: dict | None = None,
    reseller_user_id: int | None = None,
    pg_admin_username: str | None = None,
    pg_role_id: int | None = None,
    data_limit: int | None = None,
    expire_ts: int | None = None,
    hwid_limit: int | None = None,
    from_template: bool = False,
    quantity: int = 1,
    audience: str = "admin",
) -> None:
    """Gate for creating users (shop delivery or PG panel create)."""
    rid = reseller_user_id
    if rid is None and staff is not None:
        rid = reseller_id_from_staff(staff)

    try:
        await assert_billing_allows_provision(session, reseller_user_id=rid)
    except BillingError as e:
        raise _wrap(e) from e

    try:
        await _assert_volume_for_create(
            session,
            reseller_user_id=rid,
            data_limit=data_limit,
            quantity=quantity,
            audience=audience,
        )
    except VolumeAllocationError as e:
        raise _wrap(e) from e

    try:
        if staff is not None and pg_admin_username is None:
            await assert_can_create_user(
                staff,
                data_limit=data_limit,
                expire_ts=expire_ts,
                hwid_limit=hwid_limit,
                from_template=from_template,
                quantity=quantity,
                session=session,
            )
        elif pg_admin_username is not None or rid:
            await assert_reseller_can_deliver(
                pg_admin_username=pg_admin_username,
                pg_role_id=pg_role_id,
                data_limit=data_limit,
                expire_ts=expire_ts,
                hwid_limit=hwid_limit,
                from_template=from_template,
                quantity=quantity,
                session=session,
                reseller_user_id=rid,
            )
        elif staff is not None:
            await assert_can_create_user(
                staff,
                data_limit=data_limit,
                expire_ts=expire_ts,
                hwid_limit=hwid_limit,
                from_template=from_template,
                quantity=quantity,
                session=session,
            )
    except PgQuotaError as e:
        raise _wrap(e) from e


async def assert_provision_renew(
    session: AsyncSession,
    *,
    staff: dict | None = None,
    reseller_user_id: int | None = None,
    pg_admin_username: str | None = None,
    pg_role_id: int | None = None,
    data_limit: int | None = None,
    expire_ts: int | None = None,
    from_template: bool = False,
    current_data_limit: int | None = None,
    audience: str = "admin",
) -> None:
    """Gate for renewals / template re-apply."""
    rid = reseller_user_id
    if rid is None and staff is not None:
        rid = reseller_id_from_staff(staff)

    try:
        await assert_billing_allows_provision(session, reseller_user_id=rid)
    except BillingError as e:
        raise _wrap(e) from e

    if rid is not None and data_limit is not None:
        from app.services.volume_allocation import assert_new_limit_allowed

        try:
            await assert_new_limit_allowed(
                session,
                shop_id=int(rid),
                current_limit_bytes=current_data_limit,
                new_limit_bytes=data_limit,
                audience=audience,  # type: ignore[arg-type]
            )
        except VolumeAllocationError as e:
            raise _wrap(e) from e
    elif rid is not None and data_limit is None and from_template:
        try:
            await assert_volume_delta_allowed(
                session,
                shop_id=int(rid),
                delta_bytes=None,
                audience=audience,  # type: ignore[arg-type]
            )
        except VolumeAllocationError as e:
            raise _wrap(e) from e

    try:
        if staff is not None and pg_admin_username is None:
            if from_template:
                await assert_can_mutate_owned_users(staff, session=session)
            else:
                await assert_can_modify_user(
                    staff,
                    data_limit=data_limit,
                    expire_ts=expire_ts,
                    data_limit_changed=data_limit is not None,
                    expire_changed=expire_ts is not None,
                    session=session,
                )
        else:
            await assert_reseller_can_renew(
                pg_admin_username=pg_admin_username,
                pg_role_id=pg_role_id,
                data_limit=data_limit,
                expire_ts=expire_ts,
                from_template=from_template,
                session=session,
                reseller_user_id=rid,
            )
    except PgQuotaError as e:
        raise _wrap(e) from e


async def assert_provision_modify(
    session: AsyncSession,
    staff: dict,
    *,
    data_limit: int | None = None,
    expire_ts: int | None = None,
    hwid_limit: int | None = None,
    data_limit_changed: bool = False,
    expire_changed: bool = False,
    hwid_changed: bool = False,
    current_data_limit: int | None = None,
    audience: str = "admin",
) -> None:
    """Gate for PG user edit (volume / expire / HWID / plan-like changes)."""
    rid = reseller_id_from_staff(staff)
    # Only block when the mutation increases commitment (volume/time/device change)
    if data_limit_changed or expire_changed or hwid_changed:
        try:
            await assert_billing_allows_provision(session, reseller_user_id=rid)
        except BillingError as e:
            raise _wrap(e) from e
    if rid is not None and data_limit_changed:
        from app.services.volume_allocation import assert_new_limit_allowed

        try:
            await assert_new_limit_allowed(
                session,
                shop_id=int(rid),
                current_limit_bytes=current_data_limit,
                new_limit_bytes=data_limit,
                audience=audience,  # type: ignore[arg-type]
            )
        except VolumeAllocationError as e:
            raise _wrap(e) from e
    try:
        await assert_can_modify_user(
            staff,
            data_limit=data_limit,
            expire_ts=expire_ts,
            hwid_limit=hwid_limit,
            data_limit_changed=data_limit_changed,
            expire_changed=expire_changed,
            hwid_changed=hwid_changed,
            session=session,
        )
    except PgQuotaError as e:
        raise _wrap(e) from e


async def assert_provision_mutate(session: AsyncSession, staff: dict) -> None:
    """Gate for generic owned-user mutations that still commit resources (reset, etc.)."""
    rid = reseller_id_from_staff(staff)
    try:
        await assert_billing_allows_provision(session, reseller_user_id=rid)
    except BillingError as e:
        raise _wrap(e) from e
    try:
        await assert_can_mutate_owned_users(staff, session=session)
    except PgQuotaError as e:
        raise _wrap(e) from e
