from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, ResellerProfile, Role


async def make_reseller(
    session: AsyncSession,
    user: BotUser,
    *,
    commission_percent: int = 10,
    can_approve_receipts: bool = False,
    pg_admin_username: str | None = None,
) -> ResellerProfile:
    user.role = Role.RESELLER.value
    result = await session.execute(
        select(ResellerProfile).where(ResellerProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile:
        profile.commission_percent = commission_percent
        profile.can_approve_receipts = can_approve_receipts
        profile.pg_admin_username = pg_admin_username
        profile.is_active = True
    else:
        profile = ResellerProfile(
            user_id=user.id,
            commission_percent=commission_percent,
            can_approve_receipts=can_approve_receipts,
            pg_admin_username=pg_admin_username,
        )
        session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def get_reseller_profile(session: AsyncSession, user_id: int) -> ResellerProfile | None:
    result = await session.execute(
        select(ResellerProfile).where(ResellerProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()
