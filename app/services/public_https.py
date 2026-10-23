"""Public https origin for payment gateway callbacks.

Iranian PSPs (Paystar/Shaparak) often fail browser returns to non-443 ports.
Prefer a clean ``https://host`` origin over ``https://host:9000`` even when the
panel TLS metadata publishes the app listen port.
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from app.config import get_settings

# Imported as module attrs so tests can patch ``public_https.https_is_active``.
from app.services.ssl_certs import https_is_active, public_panel_base_url


def env_public_base() -> str:
    """Configured PUBLIC_BASE_URL or WEBHOOK_URL (any scheme), stripped."""
    cfg = get_settings()
    return (cfg.public_base_url or cfg.webhook_url or "").rstrip("/")


def _is_clean_https_origin(url: str) -> bool:
    """True for ``https://host`` or ``https://host:443`` (no exotic port)."""
    try:
        parts = urlparse((url or "").strip())
    except ValueError:
        return False
    if parts.scheme != "https" or not parts.hostname:
        return False
    return parts.port is None or int(parts.port) == 443


def strip_https_nondefault_port(url: str) -> str:
    """``https://host:9000/path`` → ``https://host`` (origin only, no path)."""
    raw = (url or "").strip().rstrip("/")
    try:
        parts = urlparse(raw)
    except ValueError:
        return ""
    if parts.scheme != "https" or not parts.hostname:
        return ""
    if parts.port is None or int(parts.port) == 443:
        return urlunparse(("https", parts.hostname, "", "", "", "")).rstrip("/")
    return urlunparse(("https", parts.hostname, "", "", "", "")).rstrip("/")


def https_public_base() -> str:
    """Https origin for PSP callbacks /go links, or empty when none is available.

    Preference order:
    1. Clean env https (no non-443 port)
    2. Clean live panel https
    3. Env/live with non-443 port stripped to bare host (PSP-friendly)
    4. Any remaining https env, then live panel
    """
    configured = env_public_base().strip().rstrip("/")
    live = ""
    if https_is_active():
        live = (public_panel_base_url() or "").strip().rstrip("/")

    def _https(url: str) -> str:
        return url if url.startswith("https://") else ""

    conf = _https(configured)
    liv = _https(live)

    ranked: list[str] = []

    def _add(url: str) -> None:
        u = (url or "").strip().rstrip("/")
        if u and u not in ranked:
            ranked.append(u)

    for candidate in (conf, liv):
        if candidate and _is_clean_https_origin(candidate):
            _add(candidate)
    for candidate in (conf, liv):
        if not candidate:
            continue
        stripped = strip_https_nondefault_port(candidate)
        if stripped and _is_clean_https_origin(stripped):
            _add(stripped)
    for candidate in (conf, liv):
        _add(candidate)

    return ranked[0] if ranked else ""
