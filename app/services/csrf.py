"""Double-submit CSRF tokens for cookie-authenticated panel POSTs."""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Request
from starlette.datastructures import UploadFile

CSRF_COOKIE = "csrf"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER = "x-csrf-token"


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_csrf_token(request: Request) -> str:
    """Return existing CSRF cookie value or mint one onto ``request.state``."""
    existing = (request.cookies.get(CSRF_COOKIE) or "").strip()
    if existing:
        request.state.csrf_token = existing
        return existing
    minted = getattr(request.state, "csrf_token", None)
    if isinstance(minted, str) and minted.strip():
        return minted.strip()
    token = new_csrf_token()
    request.state.csrf_token = token
    request.state.csrf_token_set = True
    return token


def read_submitted_csrf(request: Request, form: Optional[dict] = None) -> str:
    header = (request.headers.get(CSRF_HEADER) or "").strip()
    if header:
        return header
    if form is not None:
        raw = form.get(CSRF_FORM_FIELD)
        if isinstance(raw, UploadFile):
            return ""
        if raw is not None:
            return str(raw).strip()
    return ""


def csrf_tokens_match(cookie_token: str, submitted: str) -> bool:
    a = (cookie_token or "").strip()
    b = (submitted or "").strip()
    if not a or not b:
        return False
    return secrets.compare_digest(a, b)


async def extract_csrf_from_request(request: Request) -> str:
    """Best-effort CSRF from header or already-parsed / buffered form body."""
    header = (request.headers.get(CSRF_HEADER) or "").strip()
    if header:
        return header
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
        try:
            form = await request.form()
            raw = form.get(CSRF_FORM_FIELD)
            if raw is None:
                return ""
            if isinstance(raw, UploadFile):
                return ""
            return str(raw).strip()
        except Exception:
            return ""
    return ""
