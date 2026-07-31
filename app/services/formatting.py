from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def _byte_unit_table() -> tuple[tuple[float, str], ...]:
    """(divisor, Persian label) from smallest to largest."""
    return (
        (1.0, "بایت"),
        (1024.0, "کیلوبایت"),
        (1024.0**2, "مگ"),
        (1024.0**3, "گیگ"),
        (1024.0**4, "ترابایت"),
        (1024.0**5, "پتابایت"),
    )


def _pick_byte_unit(nbytes: float) -> tuple[float, str]:
    n = abs(float(nbytes))
    units = _byte_unit_table()
    chosen = units[0]
    for div, label in units:
        if n >= div:
            chosen = (div, label)
        else:
            break
    return chosen


def _fmt_unit_amount(n: float, *, precision: int | None = None) -> str:
    if precision is not None:
        return f"{n:.{precision}f}"
    if n >= 100:
        return f"{n:.0f}"
    if n >= 10:
        return f"{n:.1f}".rstrip("0").rstrip(".")
    return f"{n:.2f}".rstrip("0").rstrip(".")


def format_bytes(num: int | float | None, *, precision: int | None = None) -> str:
    """Human-readable size using IEC binary units (1024) with Persian labels."""
    if num is None:
        return "نامحدود"
    try:
        n = float(num)
    except (TypeError, ValueError):
        return "—"
    if n < 0:
        n = abs(n)
    div, label = _pick_byte_unit(n)
    if div == 1.0:
        return f"{int(round(n))} {label}"
    return f"{_fmt_unit_amount(n / div, precision=precision)} {label}"


def format_bytes_ratio(
    used: int | float | None,
    limit: int | float | None,
    *,
    precision: int | None = None,
) -> str:
    """Shared-unit used/limit string, e.g. «۱۰/۱۰۰ گیگ» or «۵۱۲/۱۰۲۴ مگ»."""
    if limit is None:
        return format_bytes(used, precision=precision)
    try:
        u = float(used or 0)
        lim = float(limit)
    except (TypeError, ValueError):
        return "—"
    if lim <= 0:
        return format_bytes(u, precision=precision)
    if u < 0:
        u = abs(u)
    div, label = _pick_byte_unit(max(u, lim))
    if div == 1.0:
        return f"{int(round(u))}/{int(round(lim))} {label}"
    left = _fmt_unit_amount(u / div, precision=precision)
    right = _fmt_unit_amount(lim / div, precision=precision)
    return f"{left}/{right} {label}"


def format_count_ratio(used: int | float | None, limit: int | float | None) -> str:
    """Integer used/limit without spaces: «۱۲/۲۰»."""
    if limit is None:
        return format_number(used)
    try:
        lim = int(limit)
    except (TypeError, ValueError):
        return format_number(used)
    if lim <= 0:
        return format_number(used)
    try:
        u = int(used or 0)
    except (TypeError, ValueError):
        u = 0
    return f"{format_number(u)}/{format_number(lim)}"


def format_gb(gb: float | int | None) -> str:
    if gb is None:
        return "نامحدود"
    try:
        n = float(gb)
    except (TypeError, ValueError):
        return "—"
    if n <= 0:
        return "نامحدود"
    return format_bytes(n * (1024**3))


def format_number(num: int | float | None) -> str:
    if num is None:
        return "—"
    try:
        if isinstance(num, float) and not num.is_integer():
            return f"{num:,.2f}".replace(",", "٬")
        return f"{int(num):,}".replace(",", "٬")
    except (TypeError, ValueError):
        return str(num)


def format_uptime(seconds: int | float | None) -> str:
    if seconds is None:
        return "—"
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return str(seconds)
    if total < 0:
        total = abs(total)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} روز")
    if hours or days:
        parts.append(f"{hours} ساعت")
    if mins or not parts:
        parts.append(f"{mins} دقیقه")
    if not days and not hours:
        parts.append(f"{secs} ثانیه")
    return " و ".join(parts)


def format_metric(key: str, value: Any) -> str:
    """Pretty-print PasarGuard / system stats by field name."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "بله" if value else "خیر"
    key_l = str(key).lower()

    if "uptime" in key_l and isinstance(value, (int, float)):
        return format_uptime(value)
    if key_l in {"cpu_usage", "cpu"} and isinstance(value, (int, float)):
        return f"{float(value):.1f}٪".replace(".", "٫")

    byte_hints = (
        "traffic",
        "bandwidth",
        "byte",
        "upload",
        "download",
        "memory",
        "mem_",
        "ram",
        "disk",
        "storage",
        "data_limit",
        "used_traffic",
        "lifetime",
    )
    if any(h in key_l for h in byte_hints) and isinstance(value, (int, float)):
        # user counts must stay numeric
        if key_l.endswith("_users") or key_l.endswith("_user") or "count" in key_l:
            return format_number(value)
        return format_bytes(value)
    if isinstance(value, float):
        return format_number(value)
    if isinstance(value, int):
        return format_number(value)
    return str(value)


STAT_LABELS_FA: dict[str, str] = {
    "version": "نسخه پنل",
    "started_at": "شروع سرویس",
    "uptime": "آپ‌تایم",
    "uptime_seconds": "آپ‌تایم",
    "system_uptime": "آپ‌تایم سیستم",
    "mem_total": "کل حافظه",
    "mem_used": "حافظه مصرفی",
    "mem_free": "حافظه آزاد",
    "memory_total": "کل حافظه",
    "memory_used": "حافظه مصرفی",
    "disk_total": "کل دیسک",
    "disk_used": "دیسک مصرفی",
    "disk_free": "دیسک آزاد",
    "cpu_usage": "مصرف پردازنده",
    "cpu_cores": "هسته‌های پردازنده",
    "total_user": "کل کاربران",
    "total_users": "کل کاربران",
    "users_total": "کل کاربران",
    "active_users": "کاربران فعال",
    "users_active": "کاربران فعال",
    "disabled_users": "کاربران غیرفعال",
    "users_disabled": "کاربران غیرفعال",
    "expired_users": "کاربران منقضی",
    "users_expired": "کاربران منقضی",
    "limited_users": "کاربران اتمام‌حجم",
    "users_limited": "کاربران اتمام‌حجم",
    "on_hold_users": "کاربران در انتظار",
    "online_users": "کاربران آنلاین",
    "users_online": "کاربران آنلاین",
    "total_admin": "تعداد ادمین",
    "admins_total": "تعداد ادمین",
    "total_node": "تعداد نود",
    "nodes_total": "تعداد نود",
    "nodes_online": "نودهای آنلاین",
    "incoming_bandwidth": "پهنای باند ورودی",
    "outgoing_bandwidth": "پهنای باند خروجی",
    "incoming_bandwidth_speed": "سرعت ورودی",
    "outgoing_bandwidth_speed": "سرعت خروجی",
    "panel_traffic": "ترافیک پنل",
    "users_active_percentage": "درصد کاربران فعال",
}


def label_stat_key(key: str) -> str:
    k = str(key)
    if k in STAT_LABELS_FA:
        return STAT_LABELS_FA[k]
    low = k.lower()
    if low in STAT_LABELS_FA:
        return STAT_LABELS_FA[low]
    known_bits = {
        "users": "کاربران",
        "user": "کاربر",
        "disabled": "غیرفعال",
        "active": "فعال",
        "expired": "منقضی",
        "limited": "محدود",
        "online": "آنلاین",
        "total": "کل",
        "nodes": "نودها",
        "node": "نود",
        "admins": "ادمین‌ها",
        "admin": "ادمین",
        "traffic": "ترافیک",
        "bandwidth": "پهنای باند",
        "incoming": "ورودی",
        "outgoing": "خروجی",
        "memory": "حافظه",
        "mem": "حافظه",
        "disk": "دیسک",
        "cpu": "پردازنده",
        "cores": "هسته‌ها",
        "usage": "مصرف",
        "version": "نسخه",
        "speed": "سرعت",
        "uptime": "آپ‌تایم",
        "seconds": "",
        "hold": "انتظار",
        "on": "",
        "used": "مصرفی",
        "free": "آزاد",
    }
    parts = [known_bits.get(p, p) for p in low.split("_") if p]
    parts = [p for p in parts if p]
    return " ".join(parts) if parts else k.replace("_", " ")


def format_stat_row(key: str, value: Any) -> tuple[str, str]:
    return label_stat_key(key), format_metric(key, value)


def format_system_stats(stats: dict | Any, *, limit: int = 40) -> str:
    """Full Persian human-readable system stats block for bot/web."""
    if not isinstance(stats, dict):
        return str(stats)
    lines: list[str] = []
    for key, val in list(stats.items())[:limit]:
        if isinstance(val, (dict, list)):
            continue
        label, pretty = format_stat_row(str(key), val)
        lines.append(f"• <b>{label}</b>: {pretty}")
    return "\n".join(lines) if lines else "آماری نیست."


TICKET_STATUS_FA = {
    "open": "باز",
    "answered": "پاسخ‌داده‌شده",
    "closed": "بسته",
}


def ticket_status_fa(status: str | None) -> str:
    if not status:
        return "نامشخص"
    return TICKET_STATUS_FA.get(str(status).lower(), str(status))


ORDER_STATUS_FA = {
    "pending": "در انتظار",
    "awaiting_receipt": "منتظر رسید",
    "awaiting_approval": "منتظر تأیید",
    "paid": "پرداخت‌شده",
    "delivered": "تحویل‌شده",
    "rejected": "ردشده",
    "cancelled": "لغوشده",
}


def order_status_fa(status: str | None) -> str:
    if not status:
        return "نامشخص"
    return ORDER_STATUS_FA.get(str(status).lower(), str(status))


NODE_STATUS_FA = {
    "connected": "متصل",
    "connecting": "در حال اتصال",
    "error": "خطا",
    "disabled": "غیرفعال",
    "healthy": "سالم",
    "unhealthy": "ناسالم",
    "online": "آنلاین",
    "offline": "آفلاین",
}


def node_status_fa(status: str | None) -> str:
    if not status:
        return "نامشخص"
    return NODE_STATUS_FA.get(str(status).lower(), str(status))


def format_toman(amount: int, currency: str = "تومان") -> str:
    """Persian money string; leading RLM keeps Telegram RTL for numeric lines."""
    return f"\u200f{format_number(amount)} {currency}"


def progress_bar(used: float, total: float | None, width: int = 10) -> str:
    if not total or total <= 0:
        filled = 0
        pct = 0
    else:
        pct = max(0, min(100, int((used / total) * 100)))
        filled = int(round((pct / 100) * width))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct}%"


def parse_expire(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = int(value)
        if ts > 10_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def format_expire(value: Any) -> str:
    dt = parse_expire(value)
    if not dt:
        return "نامحدود"
    local = dt.astimezone()
    remaining = dt - datetime.now(timezone.utc)
    days = max(0, remaining.days)
    hours = max(0, remaining.seconds // 3600)
    return f"{local.strftime('%Y/%m/%d %H:%M')} ({days} روز و {hours} ساعت)"


def format_expire_short(value: Any) -> str:
    """Compact expire for tables: date + remaining days."""
    dt = parse_expire(value)
    if not dt:
        return "—"
    remaining = dt - datetime.now(timezone.utc)
    if remaining.total_seconds() <= 0:
        return f"{dt.astimezone().strftime('%Y/%m/%d')} · منقضی"
    days = max(1, int((remaining.total_seconds() + 86399) // 86400))
    return f"{dt.astimezone().strftime('%Y/%m/%d')} · {days} روز"


def expire_remaining_days(value: Any) -> int | None:
    """Whole days left until expire (ceil); None if unlimited."""
    dt = parse_expire(value)
    if not dt:
        return None
    remaining = dt - datetime.now(timezone.utc)
    if remaining.total_seconds() <= 0:
        return 0
    return max(1, int((remaining.total_seconds() + 86399) // 86400))


def data_limit_to_gb(value: Any) -> float | None:
    if value is None or value == 0:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return round(n / (1024**3), 2)


STATUS_FA = {
    "active": "🟢 فعال",
    "disabled": "🔴 غیرفعال",
    "limited": "🟠 اتمام حجم",
    "expired": "⚫ منقضی",
    "on_hold": "🟡 در انتظار",
}


def status_label(status: str | None) -> str:
    if not status:
        return "نامشخص"
    return STATUS_FA.get(status.lower(), status)


def kv_line(emoji: str, label: str, value: str) -> str:
    """One labeled row for Telegram HTML cards (RTL-safe)."""
    return f"\u200f{emoji} <b>{label}:</b> {value}"


def info_block(lines: list[str]) -> str:
    """Join info rows with comfortable spacing."""
    clean = [ln.strip() for ln in lines if ln and str(ln).strip()]
    return "\n".join(clean)


def service_card(info: dict, currency_note: str = "") -> str:
    username = info.get("username", "—")
    status = status_label(info.get("status"))
    used = info.get("used_traffic") or 0
    limit = info.get("data_limit")
    expire = format_expire(info.get("expire"))
    bar = progress_bar(float(used), float(limit) if limit else None)
    lines = [
        f"👤 <b>{username}</b>",
        "",
        kv_line("📶", "وضعیت", status),
        kv_line("📦", "حجم", f"{format_bytes(used)} از {format_bytes(limit)}"),
        f"<code>{bar}</code>",
        kv_line("📅", "انقضا", f"<b>{expire}</b>"),
    ]
    if currency_note:
        lines.extend(["", currency_note])
    online = info.get("online_at")
    if online:
        lines.append(kv_line("⏱", "آخرین آنلاین", format_expire(online)))
    return "\n".join(lines)


def rtl_text(text: str) -> str:
    """Prefix each line with RLM so numeric-leading rows stay right-aligned in Telegram."""
    if not text:
        return text
    return "\n".join(("\u200f" + line) if line else line for line in str(text).split("\n"))


def format_message(title: str, body: str = "") -> str:
    """Pretty Telegram HTML card — bold title, soft divider, spaced body."""
    title = (title or "").strip()
    body = (body or "").strip()
    if not body:
        out = f"<b>{title}</b>" if title else ""
    elif not title:
        out = body
    else:
        out = f"<b>{title}</b>\n━━━━━━━━━━━━\n{body}"
    return rtl_text(out)
