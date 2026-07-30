"""Grant / manage web-panel access for existing PasarGuard admins."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PgStaffAccess, ResellerProfile
from app.services.web_auth import (
    hash_password,
    load_web_admin,
    validate_password_strength,
    validate_web_username,
    verify_password_hash,
)


async def list_access_rows(session: AsyncSession) -> list[PgStaffAccess]:
    result = await session.execute(select(PgStaffAccess).order_by(PgStaffAccess.id.desc()))
    return list(result.scalars().all())


async def access_by_pg_username(session: AsyncSession, pg_username: str) -> PgStaffAccess | None:
    uname = (pg_username or "").strip().lower()
    if not uname:
        return None
    result = await session.execute(
        select(PgStaffAccess).where(PgStaffAccess.pg_username == uname)
    )
    return result.scalar_one_or_none()


async def access_by_web_username(session: AsyncSession, web_username: str) -> PgStaffAccess | None:
    uname = (web_username or "").strip().lower()
    if not uname:
        return None
    result = await session.execute(
        select(PgStaffAccess).where(PgStaffAccess.web_username == uname)
    )
    return result.scalar_one_or_none()


async def access_map_by_pg(session: AsyncSession) -> dict[str, PgStaffAccess]:
    rows = await list_access_rows(session)
    return {(r.pg_username or "").lower(): r for r in rows if r.pg_username}


async def _username_taken(
    session: AsyncSession,
    web_username: str,
    *,
    exclude_id: int | None = None,
) -> str | None:
    cleaned, err = validate_web_username(web_username, lowercase=True)
    if err:
        return err
    admin_u = (load_web_admin().get("username") or "").strip().lower()
    if cleaned == admin_u:
        return "این نام کاربری برای ادمین اصلی پنل رزرو است"
    clash_reseller = await session.execute(
        select(ResellerProfile).where(ResellerProfile.web_username == cleaned)
    )
    if clash_reseller.scalar_one_or_none():
        return "این نام کاربری قبلاً برای یک نماینده گرفته شده"
    q = select(PgStaffAccess).where(PgStaffAccess.web_username == cleaned)
    if exclude_id is not None:
        q = q.where(PgStaffAccess.id != int(exclude_id))
    clash = await session.execute(q)
    if clash.scalar_one_or_none():
        return "این نام کاربری قبلاً گرفته شده"
    return None


async def upsert_web_access(
    session: AsyncSession,
    *,
    pg_username: str,
    web_username: str,
    password: str,
    note: str = "",
    is_active: bool = True,
) -> tuple[PgStaffAccess | None, str | None]:
    pg_u = (pg_username or "").strip().lower()
    if not pg_u:
        return None, "نام ادمین پاسارگارد الزامی است"
    if not (password or "").strip():
        return None, "رمز عبور الزامی است"
    ok, err = validate_password_strength(password)
    if not ok:
        return None, err

    cleaned, uerr = validate_web_username(web_username, lowercase=True)
    if uerr:
        return None, uerr

    existing = await access_by_pg_username(session, pg_u)
    taken = await _username_taken(
        session, cleaned, exclude_id=existing.id if existing else None
    )
    if taken:
        return None, taken

    if existing:
        existing.web_username = cleaned
        existing.web_password_hash = hash_password(password)
        existing.is_active = bool(is_active)
        if note is not None:
            existing.note = (note or "").strip() or None
        await session.commit()
        await session.refresh(existing)
        return existing, None

    row = PgStaffAccess(
        pg_username=pg_u,
        web_username=cleaned,
        web_password_hash=hash_password(password),
        is_active=bool(is_active),
        note=(note or "").strip() or None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row, None


async def revoke_web_access(session: AsyncSession, pg_username: str) -> bool:
    row = await access_by_pg_username(session, pg_username)
    if not row:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def set_active(session: AsyncSession, pg_username: str, active: bool) -> bool:
    row = await access_by_pg_username(session, pg_username)
    if not row:
        return False
    row.is_active = bool(active)
    await session.commit()
    return True


async def change_staff_credentials(
    session: AsyncSession,
    row: PgStaffAccess,
    *,
    old_username: str,
    current_password: str,
    new_username: str,
    new_password: str,
) -> tuple[PgStaffAccess | None, str | None]:
    if (old_username or "").strip().lower() != (row.web_username or "").lower():
        return None, "یوزر یا رمز قدیم اشتباه است"
    if not verify_password_hash(current_password or "", row.web_password_hash):
        return None, "یوزر یا رمز قدیم اشتباه است"
    ok, err = validate_password_strength(new_password or "")
    if not ok:
        return None, err
    cleaned, uerr = validate_web_username(new_username, lowercase=True)
    if uerr:
        return None, uerr
    taken = await _username_taken(session, cleaned, exclude_id=row.id)
    if taken:
        return None, taken
    row.web_username = cleaned
    row.web_password_hash = hash_password(new_password)
    await session.commit()
    await session.refresh(row)
    return row, None


async def resolve_pg_role_id_for_admin(pg_username: str) -> int | None:
    """Look up role_id for a PasarGuard admin username."""
    from app.services.pasarguard import get_pg

    try:
        admin = await get_pg().get_admin(pg_username)
    except Exception:
        return None
    if not isinstance(admin, dict):
        return None
    role = admin.get("role")
    if isinstance(role, dict) and role.get("id") is not None:
        try:
            return int(role["id"])
        except (TypeError, ValueError):
            pass
    for key in ("role_id", "admin_role_id"):
        if admin.get(key) is not None:
            try:
                return int(admin[key])
            except (TypeError, ValueError):
                pass
    return None
