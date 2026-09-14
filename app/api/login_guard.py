"""Panel login IP resolution and brute-force failure tracking.

Extracted from ``app.api.app`` so the panel factory stays focused on routing.
Lockouts are persisted under DATA_DIR so restarts / multi-worker boots share
a lockout window.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict

from fastapi import Request

from app.config import DATA_DIR, get_settings

# ip -> recent failure timestamps
_LOGIN_FAILURES: dict[str, list[float]] = defaultdict(list)
_LOGIN_WINDOW_SEC = 15 * 60
_LOGIN_MAX_FAILURES = 8
_LOGIN_LOCK_FILE = DATA_DIR / "login_lockouts.json"
_LOGIN_LOCK_MAX_KEYS = 5000


def _login_lock_load() -> None:
    """Best-effort hydrate of in-memory lockouts from disk."""
    try:
        if not _LOGIN_LOCK_FILE.is_file():
            return
        raw = json.loads(_LOGIN_LOCK_FILE.read_text(encoding="utf-8") or "{}")
        if not isinstance(raw, dict):
            return
        now = time.time()
        for key, stamps in raw.items():
            if not isinstance(key, str) or not isinstance(stamps, list):
                continue
            kept = [
                float(t)
                for t in stamps
                if isinstance(t, (int, float)) and now - float(t) < _LOGIN_WINDOW_SEC
            ]
            if kept:
                _LOGIN_FAILURES[key] = kept
    except Exception:
        logging.getLogger(__name__).debug("login lockout load failed", exc_info=True)


def _login_lock_save() -> None:
    """Persist pruned lockouts (chmod 0600). Caps key count to bound disk growth."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        now = time.time()
        pruned: dict[str, list[float]] = {}
        items = sorted(
            _LOGIN_FAILURES.items(),
            key=lambda kv: max(kv[1]) if kv[1] else 0.0,
            reverse=True,
        )
        for key, stamps in items:
            kept = [float(t) for t in stamps if now - float(t) < _LOGIN_WINDOW_SEC]
            if kept:
                pruned[key] = kept
            if len(pruned) >= _LOGIN_LOCK_MAX_KEYS:
                break
        _LOGIN_FAILURES.clear()
        _LOGIN_FAILURES.update(pruned)
        tmp = _LOGIN_LOCK_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(pruned, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _LOGIN_LOCK_FILE)
        try:
            _LOGIN_LOCK_FILE.chmod(0o600)
        except OSError:
            pass
    except Exception:
        logging.getLogger(__name__).debug("login lockout save failed", exc_info=True)


_login_lock_load()


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
    _login_lock_save()


def login_success(ip: str) -> None:
    _LOGIN_FAILURES.pop(ip, None)
    _login_lock_save()
