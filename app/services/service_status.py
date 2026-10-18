"""PasarGuard status labels shared by customer lists and service previews."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.formatting import is_on_hold_status


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    key: str
    title: str
    tone: str


SERVICE_STATUSES = (
    ServiceStatus("active", "فعال", "active"),
    ServiceStatus("disabled", "غیرفعال", "warn"),
    ServiceStatus("limited", "اتمام حجم", "warn"),
    ServiceStatus("expired", "منقضی", "blocked"),
    ServiceStatus("on_hold", "در انتظار اتصال", "neutral"),
    ServiceStatus("unknown", "وضعیت نامشخص", "neutral"),
)
_BY_KEY = {status.key: status for status in SERVICE_STATUSES}


def service_status(raw: str | None) -> ServiceStatus:
    key = str(raw or "").strip().lower()
    if is_on_hold_status(key):
        key = "on_hold"
    return _BY_KEY.get(key, _BY_KEY["unknown"])
