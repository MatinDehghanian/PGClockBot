"""Redact secrets from logs and user-facing error strings."""

from __future__ import annotations

import re

_BOT_TOKEN_RE = re.compile(r"\b(\d{6,}:[A-Za-z0-9_-]{20,})\b")
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~\-+/=]{8,}")
_PASSWORD_QS_RE = re.compile(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key)=([^&\s]+)")
_BASIC_AUTH_RE = re.compile(r"(://)([^:/@\s]+):([^@/\s]+)(@)")


def redact(text: object, *, limit: int = 400) -> str:
    s = "" if text is None else str(text)
    s = _BOT_TOKEN_RE.sub("<bot-token>", s)
    s = _BEARER_RE.sub(r"\1<redacted>", s)
    s = _PASSWORD_QS_RE.sub(r"\1=<redacted>", s)
    s = _BASIC_AUTH_RE.sub(r"\1\2:<redacted>\4", s)
    s = s.replace("\n", " ").strip()
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s
