"""Shared security helpers: placeholders, CSRF/origin checks, request limits."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

# Documented / example values that must never complete setup or become live creds.
PLACEHOLDER_BOT_TOKENS = frozenset(
    {
        "123456:ABC-DEF",
        "0000000000:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "YOUR_BOT_TOKEN",
        "change-me",
    }
)
PLACEHOLDER_PASSWORDS = frozenset(
    {
        "Admin!234",
        "admin",
        "password",
        "Password1!",
        "change-me",
        "changeme",
        "12345678",
        "YourPassword",
    }
)
PLACEHOLDER_SECRETS = frozenset(
    {
        "",
        "change-me",
        "change-this-long-random-secret",
        "secret",
        "pgclock-secret",
    }
)

# Max JSON body for Telegram webhook (Telegram updates are small).
WEBHOOK_MAX_BODY_BYTES = 256 * 1024
# Soft ceiling for unauthenticated form posts (login/setup) — DoS guard.
PUBLIC_FORM_MAX_BODY_BYTES = 256 * 1024


def is_placeholder_bot_token(token: str | None) -> bool:
    t = (token or "").strip()
    if not t:
        return True
    if t in PLACEHOLDER_BOT_TOKENS:
        return True
    # Telegram tokens look like <digits>:<secret>
    if ":" not in t:
        return True
    left, _, right = t.partition(":")
    if not left.isdigit() or len(right) < 20:
        return True
    if "XXX" in t.upper() or "YOUR_" in t.upper():
        return True
    return False


def is_placeholder_password(password: str | None) -> bool:
    p = (password or "").strip()
    if not p:
        return True
    return p in PLACEHOLDER_PASSWORDS


def is_placeholder_secret(secret: str | None) -> bool:
    return (secret or "").strip() in PLACEHOLDER_SECRETS


def request_host_allowed(request_host: str | None, origin_or_referer: str | None) -> bool:
    """True when Origin/Referer host matches the request Host (CSRF defense-in-depth)."""
    if not origin_or_referer:
        return False
    try:
        parsed = urlparse(origin_or_referer)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    src = (parsed.netloc or "").strip().lower()
    dst = (request_host or "").strip().lower()
    if not src or not dst:
        return False
    # Strip default ports for comparison
    for port in (":80", ":443"):
        if src.endswith(port) and parsed.scheme == ("http" if port == ":80" else "https"):
            src = src[: -len(port)]
        if dst.endswith(port):
            dst = dst[: -len(port)]
    return src == dst


def content_length_ok(content_length: str | None, limit: int) -> bool:
    if content_length is None or content_length == "":
        return True  # chunked / unknown — route-level caps still apply
    try:
        return int(content_length) <= limit
    except (TypeError, ValueError):
        return False


def is_public_ip(host: str) -> bool:
    """Best-effort: False for loopback/link-local/private/reserved. Hostnames → True."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def pg_url_has_userinfo(url: str) -> bool:
    try:
        return bool(urlparse(url).username or urlparse(url).password)
    except Exception:
        return False
