"""Panel login IP resolution and brute-force failure tracking.

Extracted from ``app.api.app`` so the panel factory stays focused on routing.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request

from app.config import get_settings

# ip -> recent failure timestamps (process-local; fine for single-worker panels)
_LOGIN_FAILURES: dict[str, list[float]] = defaultdict(list)
_LOGIN_WINDOW_SEC = 15 * 60
_LOGIN_MAX_FAILURES = 8


def client_ip(request: Request) -> str:
    """Best-effort real client IP, resistant to X-Forwarded-For spoofing.

    X-Forwarded-For is fully attacker-controlled except for the hop(s) your
    own trusted reverse proxy appends. Reading the LEFT-most entry (the
    classic mistake) lets any client claim to be any IP — including
    loopback/private ranges, which would bypass login lockouts and the
    setup-wizard local-IP auto-open gate. Instead we read the entry counted
    from the RIGHT that corresponds to ``trust_proxy_hops`` (default: a
    single reverse proxy directly in front of the app).
    """
    try:
        settings = get_settings()
        if settings.trust_proxy:
            raw = request.headers.get("x-forwarded-for") or ""
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            hops = max(1, int(getattr(settings, "trust_proxy_hops", 1) or 1))
            if len(parts) >= hops:
                candidate = parts[-hops]
                if candidate:
                    return candidate
    except Exception:
        pass
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def login_blocked(ip: str) -> bool:
    now = time.time()
    stamps = [t for t in _LOGIN_FAILURES.get(ip, []) if now - t < _LOGIN_WINDOW_SEC]
    _LOGIN_FAILURES[ip] = stamps
    return len(stamps) >= _LOGIN_MAX_FAILURES


def login_fail(ip: str) -> None:
    now = time.time()
    stamps = [t for t in _LOGIN_FAILURES.get(ip, []) if now - t < _LOGIN_WINDOW_SEC]
    stamps.append(now)
    _LOGIN_FAILURES[ip] = stamps


def login_success(ip: str) -> None:
    _LOGIN_FAILURES.pop(ip, None)
