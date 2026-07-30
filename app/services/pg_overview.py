"""Build reseller-facing PasarGuard overview metrics (no server/hardware stats)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.formatting import format_bytes, format_expire, format_number, parse_expire
from app.services.pasarguard import get_pg


_SERVER_STAT_KEYS = {
    "version",
    "started_at",
    "uptime",
    "uptime_seconds",
    "system_uptime",
    "mem_total",
    "mem_used",
    "mem_free",
    "memory_total",
    "memory_used",
    "memory_free",
    "disk_total",
    "disk_used",
    "disk_free",
    "cpu_usage",
    "cpu_cores",
    "cpu",
    "incoming_bandwidth",
    "outgoing_bandwidth",
    "incoming_bandwidth_speed",
    "outgoing_bandwidth_speed",
    "speed",
    "load",
    "load_avg",
}


def is_server_stat_key(key: str) -> bool:
    k = (key or "").strip().lower()
    if k in _SERVER_STAT_KEYS:
        return True
    hints = ("mem_", "memory", "disk", "cpu", "uptime", "bandwidth", "load_avg", "ram")
    return any(h in k for h in hints)


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _role_limits(admin: dict | None, role: dict | None) -> dict:
    from app.services.pg_quota import merge_role_limits

    return merge_role_limits(admin, role)

def _meter(
    *,
    label: str,
    used: int | None,
    limit: int | None,
    used_label: str,
    remain_label: str,
    format_value,
) -> dict[str, Any]:
    has_limit = limit is not None and int(limit) > 0
    used_v = int(used or 0)
    remain = None
    pct = None
    if has_limit:
        lim = int(limit)
        remain = max(0, lim - used_v)
        pct = min(100.0, (used_v / lim) * 100.0) if lim else 0.0
    return {
        "label": label,
        "has_limit": has_limit,
        "used": used_v,
        "limit": int(limit) if has_limit else None,
        "remain": remain,
        "pct": pct,
        "used_text": format_value(used_v),
        "limit_text": format_value(limit) if has_limit else "نامحدود",
        "remain_text": format_value(remain) if remain is not None else "—",
        "used_label": used_label,
        "remain_label": remain_label,
    }


def _format_duration(seconds: float | int | None) -> str:
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


def _time_meter(expire_raw: Any, created_raw: Any = None) -> dict[str, Any] | None:
    exp = parse_expire(expire_raw)
    if not exp:
        return None
    now = datetime.now(timezone.utc)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    remain_sec = max(0.0, (exp - now).total_seconds())
    created = parse_expire(created_raw) if created_raw is not None else None
    used_sec = None
    pct = None
    total_sec = None
    if created is not None:
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        total_sec = max(1.0, (exp - created).total_seconds())
        used_sec = max(0.0, min(total_sec, (now - created).total_seconds()))
        pct = min(100.0, (used_sec / total_sec) * 100.0)
        remain_sec = max(0.0, total_sec - used_sec)
    expire_text = format_expire(expire_raw)
    return {
        "label": "زمان",
        "has_limit": True,
        "expire_text": expire_text,
        "total_sec": total_sec,
        "total_text": _format_duration(total_sec) if total_sec is not None else expire_text,
        "remain_sec": remain_sec,
        "remain_text": _format_duration(remain_sec) if remain_sec > 0 else "منقضی",
        "used_sec": used_sec,
        "used_text": _format_duration(used_sec) if used_sec is not None else "—",
        "pct": pct,
        "used_label": "مصرف‌شده",
        "remain_label": "باقی‌مانده",
    }


_STATUS_LABELS = {
    "active": ("فعال", "active"),
    "limited": ("محدود", "warn"),
    "disabled": ("غیرفعال", "danger"),
    "expired": ("منقضی", "danger"),
    "on_hold": ("معلق", "warn"),
}


def _status_meta(raw: Any) -> tuple[str | None, str | None]:
    if raw is None or raw == "":
        return None, None
    key = str(raw).strip().lower()
    if key in _STATUS_LABELS:
        return _STATUS_LABELS[key]
    return str(raw), "neutral"


async def build_reseller_pg_overview(staff: dict) -> dict[str, Any]:
    """Metrics for a staff member's own PG admin account (reseller or pg_staff)."""
    owner = str(staff.get("pg_admin_username") or "").strip()
    out: dict[str, Any] = {
        "username": owner or None,
        "ready": False,
        "error": None,
        "users": None,
        "traffic": None,
        "time": None,
        "status": None,
        "status_label": None,
        "status_badge": None,
        "lifetime_text": None,
        "role_name": None,
    }
    if not owner:
        out["error"] = "ادمین پاسارگارد برای این حساب تنظیم نشده است"
        return out

    try:
        pg = get_pg()
        admin = await pg.get_admin(owner)
        if not admin:
            out["error"] = f"ادمین «{owner}» در پاسارگارد یافت نشد"
            return out

        role_id = staff.get("pg_role_id")
        # Prefer embedded role on admin payload
        role = admin.get("role") if isinstance(admin.get("role"), dict) else None
        if not role and role_id:
            try:
                role = await pg.get_admin_role(int(role_id))
            except Exception:
                role = None

        limits = _role_limits(admin, role)
        total_users = _as_int(admin.get("total_users")) or _as_int(admin.get("users_count")) or 0
        max_users = (
            _as_int(limits.get("max_users"))
            or _as_int(limits.get("users_max"))
            or _as_int(admin.get("max_users"))
        )
        used_traffic = (
            _as_int(admin.get("used_traffic"))
            or _as_int(admin.get("traffic_used"))
            or 0
        )
        data_limit = (
            _as_int(admin.get("data_limit"))
            or _as_int(limits.get("data_limit"))
            or _as_int(limits.get("max_traffic"))
            or _as_int(limits.get("traffic_limit"))
        )
        lifetime = _as_int(admin.get("lifetime_used_traffic"))

        # Surface role name for UI
        role_name = None
        if isinstance(role, dict):
            role_name = role.get("name") or role.get("title")
        elif isinstance(admin.get("role"), dict):
            role_name = admin["role"].get("name") or admin["role"].get("title")
        out["role_name"] = role_name

        out["ready"] = True
        status_raw = admin.get("status") or ("limited" if admin.get("is_limited") else None)
        out["status"] = status_raw
        label, badge = _status_meta(status_raw)
        out["status_label"] = label
        out["status_badge"] = badge
        out["users"] = _meter(
            label="کاربران VPN",
            used=total_users,
            limit=max_users,
            used_label="مصرف‌شده",
            remain_label="باقی‌مانده",
            format_value=lambda v: format_number(v) if v is not None else "—",
        )
        out["traffic"] = _meter(
            label="حجم کل",
            used=used_traffic,
            limit=data_limit,
            used_label="مصرف‌شده",
            remain_label="باقی‌مانده",
            format_value=format_bytes,
        )
        if lifetime is not None:
            out["lifetime_text"] = format_bytes(lifetime)

        expire_raw = (
            admin.get("expire")
            or admin.get("expire_date")
            or admin.get("expired_at")
            or admin.get("expires_at")
        )
        out["time"] = _time_meter(
            expire_raw,
            admin.get("created_at") or admin.get("created"),
        )
        return out
    except Exception as e:
        out["error"] = str(e)
        return out
