"""Enforce PasarGuard admin role quotas for restricted staff.

Mirrors PasarGuard ``RoleLimits`` + limited-admin write gate so resellers
(and credentialed staff) cannot exceed the same role limits when acting
through PGClock — whether via own credentials or (legacy) owner-token paths.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.formatting import format_bytes


class PgQuotaError(Exception):
    """Raised when a staff action would violate PasarGuard admin quotas."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _format_duration_fa(seconds: float | int | None) -> str:
    if seconds is None:
        return "—"
    try:
        s = int(max(0, float(seconds)))
    except (TypeError, ValueError):
        return "—"
    days, rem = divmod(s, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} روز")
    if hours:
        parts.append(f"{hours} ساعت")
    if mins and not days:
        parts.append(f"{mins} دقیقه")
    if not parts:
        return "کمتر از یک دقیقه"
    return " و ".join(parts[:2])


def merge_role_limits(admin: dict | None, role: dict | None) -> dict[str, Any]:
    """Merge role.limits with admin.permission_overrides (overrides win when set).

    Same resolution order as PasarGuard ``get_effective_limits``.
    """
    limits: dict[str, Any] = {}
    role_limits = None
    if isinstance(role, dict):
        role_limits = role.get("limits")
    if role_limits is None and isinstance(admin, dict):
        embedded = admin.get("role")
        if isinstance(embedded, dict):
            role_limits = embedded.get("limits")
    if isinstance(role_limits, dict):
        limits.update(role_limits)

    overrides = (admin or {}).get("permission_overrides") if isinstance(admin, dict) else None
    if isinstance(overrides, dict):
        for k, v in overrides.items():
            if v is not None:
                limits[k] = v
    return limits


def hwid_bounds(limits: dict[str, Any]) -> tuple[int | None, int | None]:
    """Return (min_hwid, max_hwid) from role limits (aliases supported)."""
    hmin = (
        _as_int(limits.get("min_hwid_per_user"))
        or _as_int(limits.get("hwid_limit_min"))
        or _as_int(limits.get("min_devices"))
    )
    hmax = (
        _as_int(limits.get("max_hwid_per_user"))
        or _as_int(limits.get("hwid_limit_max"))
        or _as_int(limits.get("max_devices"))
        or _as_int(limits.get("device_limit"))
    )
    return hmin, hmax


def _admin_is_limited(admin: dict) -> bool:
    status = str(admin.get("status") or "").strip().lower()
    if status == "limited" or admin.get("is_limited") is True:
        return True
    # Defensive: treat exhausted admin traffic as limited even if status lags.
    data_limit = _as_int(admin.get("data_limit"))
    used = _as_int(admin.get("used_traffic")) or _as_int(admin.get("traffic_used")) or 0
    if data_limit is not None and data_limit > 0 and used >= data_limit:
        return True
    return False


def _admin_is_disabled(admin: dict) -> bool:
    if admin.get("enabled") is False or admin.get("is_disabled") is True:
        return True
    if admin.get("is_active") is False:
        return True
    status = str(admin.get("status") or "").strip().lower()
    return status in {"disabled", "inactive", "deleted", "banned"}


def assert_admin_can_write(admin: dict | None, role: dict | None = None) -> None:
    """Block mutations when the PG admin is disabled or limited (PG write gate)."""
    if not isinstance(admin, dict) or not admin:
        raise PgQuotaError("ادمین پاسارگارد برای این حساب یافت نشد")
    if _admin_is_disabled(admin):
        raise PgQuotaError("حساب ادمین پاسارگارد شما غیرفعال است و امکان تغییر ندارید")
    if _admin_is_limited(admin):
        disabled_when = False
        for src in (role, admin.get("role") if isinstance(admin.get("role"), dict) else None):
            if isinstance(src, dict) and src.get("disabled_when_limited"):
                disabled_when = True
                break
        if disabled_when:
            raise PgQuotaError(
                "حساب شما محدود شده و دسترسی کامل قطع است — با ادمین اصلی تماس بگیرید"
            )
        raise PgQuotaError(
            "حساب شما محدود شده است (سهمیه پر شده) و امکان ساخت یا تغییر کاربر ندارید"
        )


def _check_data_limit_bounds(
    limits: dict[str, Any],
    data_limit: int | None,
    *,
    require_finite: bool,
) -> None:
    data_max = _as_int(limits.get("data_limit_max"))
    data_min = _as_int(limits.get("data_limit_min"))
    unlimited = data_limit is None or data_limit <= 0

    if data_max is not None and data_max > 0 and require_finite and unlimited:
        raise PgQuotaError(
            f"حجم کاربر نمی‌تواند نامحدود باشد؛ حداکثر {format_bytes(data_max)}"
        )
    if not unlimited:
        assert data_limit is not None
        if data_min is not None and data_min > 0 and data_limit < data_min:
            raise PgQuotaError(
                f"حجم کاربر باید حداقل {format_bytes(data_min)} باشد"
            )
        if data_max is not None and data_max > 0 and data_limit > data_max:
            raise PgQuotaError(
                f"حجم کاربر نمی‌تواند بیشتر از {format_bytes(data_max)} باشد"
            )


def _check_expire_bounds(
    limits: dict[str, Any],
    expire_ts: int | None,
    *,
    require_finite: bool,
) -> None:
    expire_max = _as_int(limits.get("expire_max"))
    expire_min = _as_int(limits.get("expire_min"))
    unlimited = expire_ts is None or expire_ts <= 0

    if expire_max is not None and expire_max > 0 and require_finite and unlimited:
        raise PgQuotaError(
            f"مدت کاربر نمی‌تواند نامحدود باشد؛ حداکثر {_format_duration_fa(expire_max)} از الان"
        )
    if not unlimited:
        assert expire_ts is not None
        now = datetime.now(timezone.utc).timestamp()
        seconds = float(expire_ts) - now
        if expire_min is not None and expire_min > 0 and seconds < expire_min:
            raise PgQuotaError(
                f"مدت کاربر باید حداقل {_format_duration_fa(expire_min)} از الان باشد"
            )
        if expire_max is not None and expire_max > 0 and seconds > expire_max:
            raise PgQuotaError(
                f"مدت کاربر نمی‌تواند بیشتر از {_format_duration_fa(expire_max)} از الان باشد"
            )


def _check_hwid_bounds(
    limits: dict[str, Any],
    hwid_limit: int | None,
    *,
    require_finite: bool,
) -> None:
    """Enforce PasarGuard RoleLimits min/max HWID (device) per user."""
    hmin, hmax = hwid_bounds(limits)
    # None or 0 ⇒ unlimited (common PG / panel convention)
    unlimited = hwid_limit is None or hwid_limit <= 0

    if hmax is not None and hmax > 0 and require_finite and unlimited:
        raise PgQuotaError(
            f"سقف دستگاه (HWID) نمی‌تواند نامحدود باشد؛ حداکثر {hmax}"
        )
    if not unlimited:
        assert hwid_limit is not None
        if hmin is not None and hmin > 0 and hwid_limit < hmin:
            raise PgQuotaError(f"سقف دستگاه (HWID) باید حداقل {hmin} باشد")
        if hmax is not None and hmax > 0 and hwid_limit > hmax:
            raise PgQuotaError(f"سقف دستگاه (HWID) نمی‌تواند بیشتر از {hmax} باشد")


def _check_max_users(admin: dict, limits: dict[str, Any], *, need: int = 1) -> None:
    max_users = _as_int(limits.get("max_users")) or _as_int(admin.get("max_users"))
    if max_users is None or max_users <= 0:
        return
    current = (
        _as_int(admin.get("total_users"))
        or _as_int(admin.get("users_count"))
        or 0
    )
    need_n = max(1, int(need or 1))
    if current + need_n - 1 >= max_users:
        remain = max(0, max_users - current)
        raise PgQuotaError(
            f"سقف تعداد کاربران شما پر شده است (حداکثر {max_users}"
            + (f" — ظرفیت باقی‌مانده {remain}" if remain else "")
            + ")"
        )


async def _load_admin_and_role(staff: dict) -> tuple[dict, dict | None]:
    owner = str(staff.get("pg_admin_username") or "").strip()
    if not owner:
        raise PgQuotaError("ادمین پاسارگارد برای این حساب تنظیم نشده است")

    from app.services.pasarguard import get_pg

    pg = get_pg()
    admin = await pg.get_admin(owner)
    if not isinstance(admin, dict) or not admin:
        raise PgQuotaError(f"ادمین «{owner}» در پاسارگارد یافت نشد")

    role: dict | None = admin.get("role") if isinstance(admin.get("role"), dict) else None
    role_id = staff.get("pg_role_id")
    if role is None and admin.get("role_id") is not None:
        role_id = role_id or admin.get("role_id")
    if (role is None or not role.get("limits")) and role_id:
        try:
            fetched = await pg.get_admin_role(int(role_id))
            if isinstance(fetched, dict):
                role = fetched
        except Exception:
            pass
    return admin, role


async def load_staff_limit_snapshot(staff: dict) -> dict[str, Any]:
    """Return the actor's effective live PasarGuard limits for UI/policy use."""
    if not staff_needs_quota_check(staff):
        return {
            "restricted": False,
            "admin": None,
            "role": None,
            "limits": {},
            "max_users": None,
            "current_users": None,
            "remaining_users": None,
            "account_data_limit": None,
            "account_used_traffic": None,
            "account_remaining_traffic": None,
            "per_user_data_min": None,
            "per_user_data_max": None,
            "per_user_expire_min": None,
            "per_user_expire_max": None,
            "hwid_min": None,
            "hwid_max": None,
        }

    admin, role = await _load_admin_and_role(staff)
    limits = merge_role_limits(admin, role)
    max_users = _as_int(limits.get("max_users")) or _as_int(admin.get("max_users"))
    current_users = (
        _as_int(admin.get("total_users"))
        or _as_int(admin.get("users_count"))
        or 0
    )
    account_data_limit = _as_int(admin.get("data_limit")) or _as_int(
        limits.get("data_limit")
    )
    used_traffic = _as_int(admin.get("used_traffic")) or _as_int(
        admin.get("traffic_used")
    ) or 0
    remaining_users = (
        max(0, int(max_users) - int(current_users))
        if max_users is not None and max_users > 0
        else None
    )
    remaining_traffic = (
        max(0, int(account_data_limit) - int(used_traffic))
        if account_data_limit is not None and account_data_limit > 0
        else None
    )
    hmin, hmax = hwid_bounds(limits)
    return {
        "restricted": True,
        "admin": admin,
        "role": role,
        "limits": limits,
        "max_users": max_users,
        "current_users": current_users,
        "remaining_users": remaining_users,
        "account_data_limit": account_data_limit,
        "account_used_traffic": used_traffic,
        "account_remaining_traffic": remaining_traffic,
        "per_user_data_min": _as_int(limits.get("data_limit_min")),
        "per_user_data_max": _as_int(limits.get("data_limit_max")),
        "per_user_expire_min": _as_int(limits.get("expire_min")),
        "per_user_expire_max": _as_int(limits.get("expire_max")),
        "hwid_min": hmin,
        "hwid_max": hmax,
    }


async def assert_user_plan_within_limits(
    staff: dict,
    *,
    data_limit: int | None,
    duration_days: int | None,
    label: str = "پلن",
) -> None:
    """Reject plan definitions that exceed the live PG per-user limits."""
    if not staff_needs_quota_check(staff):
        return
    admin, role = await _load_admin_and_role(staff)
    assert_admin_can_write(admin, role)
    limits = merge_role_limits(admin, role)
    expire_ts = None
    days = int(duration_days or 0)
    if days > 0:
        expire_ts = int(datetime.now(timezone.utc).timestamp()) + days * 86400
    try:
        _check_data_limit_bounds(limits, data_limit, require_finite=True)
        _check_expire_bounds(limits, expire_ts, require_finite=True)
    except PgQuotaError as exc:
        raise PgQuotaError(f"{label}: {exc.message}") from exc


async def assert_custom_plan_range_within_limits(
    staff: dict,
    *,
    min_gb: float,
    max_gb: float,
    min_days: int,
    max_days: int,
    label: str = "پلن دلخواه",
) -> None:
    """Validate custom-plan range settings against the live PG per-user limits."""
    if max_gb < min_gb:
        raise PgQuotaError(f"{label}: حداکثر حجم نمی‌تواند کمتر از حداقل حجم باشد")
    if max_days < min_days:
        raise PgQuotaError(f"{label}: حداکثر مدت نمی‌تواند کمتر از حداقل مدت باشد")

    def _bytes(gb: float) -> int:
        return int(float(gb) * (1024**3))

    await assert_user_plan_within_limits(
        staff,
        data_limit=_bytes(min_gb),
        duration_days=int(min_days),
        label=f"{label} (حداقل)",
    )
    await assert_user_plan_within_limits(
        staff,
        data_limit=_bytes(max_gb),
        duration_days=int(max_days),
        label=f"{label} (حداکثر)",
    )


def staff_needs_quota_check(staff: dict) -> bool:
    """Full platform Owner (true PasarGuard sudo) acts as sudo — no PG capacity gate.

    A *Hybrid* Owner — ``role="admin"`` whose ``.env`` PasarGuard account is
    itself a limited admin (``pg_is_owner`` explicitly ``False``, set by
    ``pg_access.enrich_platform_admin_staff``) — must be checked exactly like
    any other restricted admin. Skipping the check for every ``role="admin"``
    used to mean a Hybrid Owner would only discover their own max_users /
    data-cap by PasarGuard's raw rejection instead of the same friendly
    Persian message resellers/pg_staff already get.

    Any non-admin staff must be checked — even when ``pg_admin_username`` is
    missing (that case fails closed in ``_load_admin_and_role``). Missing/
    unset ``pg_is_owner`` (legacy/unenriched staff dict, or a genuine
    non-Hybrid single-owner deployment) still defaults to sudo, preserving
    prior behavior for the common case.
    """
    if staff.get("role") != "admin":
        return True
    return staff.get("pg_is_owner") is False


async def assert_can_create_user(
    staff: dict,
    *,
    data_limit: int | None = None,
    expire_ts: int | None = None,
    hwid_limit: int | None = None,
    from_template: bool = False,
    quantity: int = 1,
) -> None:
    """Enforce quotas before creating a user that will be owned by this staff."""
    if not staff_needs_quota_check(staff):
        return

    admin, role = await _load_admin_and_role(staff)
    assert_admin_can_write(admin, role)
    limits = merge_role_limits(admin, role)
    _check_max_users(admin, limits, need=max(1, int(quantity or 1)))

    if from_template:
        # PasarGuard: template create only checks max_users (+ write gate).
        # HWID/volume come from the template; PG enforces when authenticated as admin.
        return

    _check_data_limit_bounds(limits, data_limit, require_finite=True)
    _check_expire_bounds(limits, expire_ts, require_finite=True)
    # When the form omits HWID but the role caps devices, default to the role max
    # so existing UIs do not accidentally create unlimited-device users.
    hmin, hmax = hwid_bounds(limits)
    effective_hwid = hwid_limit
    if (effective_hwid is None or effective_hwid <= 0) and hmax is not None and hmax > 0:
        effective_hwid = hmax
    elif (effective_hwid is None or effective_hwid <= 0) and hmin is not None and hmin > 0:
        effective_hwid = hmin
    _check_hwid_bounds(limits, effective_hwid, require_finite=True)


async def assert_can_modify_user(
    staff: dict,
    *,
    data_limit: int | None = None,
    expire_ts: int | None = None,
    hwid_limit: int | None = None,
    data_limit_changed: bool = True,
    expire_changed: bool = True,
    hwid_changed: bool = True,
) -> None:
    """Enforce per-user volume/time/HWID bounds before modify (no max_users check)."""
    if not staff_needs_quota_check(staff):
        return

    admin, role = await _load_admin_and_role(staff)
    assert_admin_can_write(admin, role)
    limits = merge_role_limits(admin, role)

    _check_data_limit_bounds(
        limits,
        data_limit,
        require_finite=data_limit_changed,
    )
    _check_expire_bounds(
        limits,
        expire_ts,
        require_finite=expire_changed,
    )
    if hwid_changed:
        _check_hwid_bounds(limits, hwid_limit, require_finite=True)


async def assert_can_mutate_owned_users(staff: dict) -> None:
    """Block enable/disable/reset/revoke/delete when admin is limited/disabled."""
    if not staff_needs_quota_check(staff):
        return
    admin, role = await _load_admin_and_role(staff)
    assert_admin_can_write(admin, role)


async def assert_reseller_can_deliver(
    *,
    pg_admin_username: str | None,
    pg_role_id: int | None = None,
    data_limit: int | None = None,
    expire_ts: int | None = None,
    hwid_limit: int | None = None,
    from_template: bool = False,
    quantity: int = 1,
) -> None:
    """Quota check for shop delivery assigned to a reseller PG admin.

    Fail closed when the shop has no PG admin link — otherwise create-as-owner
    would bypass every role quota.
    """
    uname = str(pg_admin_username or "").strip()
    if not uname:
        raise PgQuotaError(
            "ادمین پاسارگارد برای این فروشگاه تنظیم نشده است — تحویل ممکن نیست"
        )
    staff = {
        "role": "reseller",
        "pg_admin_username": uname,
        "pg_role_id": pg_role_id,
    }
    await assert_can_create_user(
        staff,
        data_limit=data_limit,
        expire_ts=expire_ts,
        hwid_limit=hwid_limit,
        from_template=from_template,
        quantity=quantity,
    )


async def assert_reseller_can_renew(
    *,
    pg_admin_username: str | None,
    pg_role_id: int | None = None,
    data_limit: int | None = None,
    expire_ts: int | None = None,
    hwid_limit: int | None = None,
    from_template: bool = False,
) -> None:
    """Quota check for shop renewal modifying a reseller-owned user."""
    uname = str(pg_admin_username or "").strip()
    if not uname:
        raise PgQuotaError(
            "ادمین پاسارگارد برای این فروشگاه تنظیم نشده است — تمدید ممکن نیست"
        )
    staff = {
        "role": "reseller",
        "pg_admin_username": uname,
        "pg_role_id": pg_role_id,
    }
    if from_template:
        await assert_can_mutate_owned_users(staff)
        return
    await assert_can_modify_user(
        staff,
        data_limit=data_limit,
        expire_ts=expire_ts,
        hwid_limit=hwid_limit,
        data_limit_changed=data_limit is not None,
        expire_changed=expire_ts is not None,
        hwid_changed=hwid_limit is not None,
    )
