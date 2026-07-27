from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def format_bytes(num: int | float | None) -> str:
    if num is None:
        return "∞"
    n = float(num)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if abs(n) < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} PB"


def format_toman(amount: int, currency: str = "تومان") -> str:
    return f"{amount:,} {currency}".replace(",", "٬")


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
        # unix seconds
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
    """
    کارت پیام فارسی با ظاهر مرتب و وسط‌چین‌مانند.
    (تلگرام CSS ندارد؛ با جداکننده و نقل‌قول بصری می‌سازیم.)
    """
    sep = "┄┄┄┄┄┄┄┄┄┄┄┄"
    parts = [f"<b>{title}</b>", f"<code>{sep}</code>"]
    body = (body or "").strip()
    if body:
        parts.append(f"<blockquote>{body}</blockquote>")
        parts.append(f"<code>{sep}</code>")
    return "\n".join(parts)
