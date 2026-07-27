from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def format_bytes(num: int | float | None, *, precision: int | None = None) -> str:
    """Human-readable size using IEC binary units (1024): B, KB, MB, GB, TB, PB."""
    if num is None:
        return "نامحدود"
    try:
        n = float(num)
    except (TypeError, ValueError):
        return "—"
    if n < 0:
        n = abs(n)
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    for i, unit in enumerate(units):
        if n < 1024 or i == len(units) - 1:
            if unit == "B":
                return f"{int(round(n))} B"
            if precision is not None:
                return f"{n:.{precision}f} {unit}"
            if n >= 100:
                val = f"{n:.0f}"
            elif n >= 10:
                val = f"{n:.1f}"
            else:
                val = f"{n:.2f}".rstrip("0").rstrip(".")
            return f"{val} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


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


def format_metric(key: str, value: Any) -> str:
    """Pretty-print PasarGuard / system stats by field name."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "بله" if value else "خیر"
    key_l = str(key).lower()
    byte_hints = (
        "traffic",
        "bandwidth",
        "byte",
        "upload",
        "download",
        "memory",
        "ram",
        "disk",
        "storage",
        "data_limit",
        "used_traffic",
        "lifetime",
    )
    if any(h in key_l for h in byte_hints) and isinstance(value, (int, float)):
        # tiny ints like counts should not become "B"
        if "count" in key_l or "users" in key_l or "nodes" in key_l:
            return format_number(value)
        if abs(float(value)) >= 1024 or "traffic" in key_l or "byte" in key_l or "memory" in key_l:
            return format_bytes(value)
    if isinstance(value, float):
        return format_number(value)
    if isinstance(value, int):
        return format_number(value)
    return str(value)


def format_toman(amount: int, currency: str = "تومان") -> str:
    return f"{format_number(amount)} {currency}"


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


def service_card(info: dict, currency_note: str = "") -> str:
    username = info.get("username", "—")
    status = status_label(info.get("status"))
    used = info.get("used_traffic") or 0
    limit = info.get("data_limit")
    expire = format_expire(info.get("expire"))
    lines = [
        f"👤 <b>{username}</b>",
        f"وضعیت: {status}",
        f"حجم: {format_bytes(used)} / {format_bytes(limit)}",
        progress_bar(float(used), float(limit) if limit else None),
        f"انقضا: {expire}",
    ]
    if currency_note:
        lines.append(currency_note)
    online = info.get("online_at")
    if online:
        lines.append(f"آخرین آنلاین: {format_expire(online)}")
    return "\n".join(lines)


def format_message(title: str, body: str = "") -> str:
    sep = "┄┄┄┄┄┄┄┄┄┄┄┄"
    parts = [f"<b>{title}</b>", f"<code>{sep}</code>"]
    body = (body or "").strip()
    if body:
        parts.append(f"<blockquote>{body}</blockquote>")
        parts.append(f"<code>{sep}</code>")
    return "\n".join(parts)
