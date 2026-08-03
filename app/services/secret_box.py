"""Encrypt small secrets at rest (reseller PG passwords) using WEB_SECRET."""

from __future__ import annotations

import base64
import hashlib
import logging

logger = logging.getLogger(__name__)


def _fernet():
    from cryptography.fernet import Fernet

    from app.config import get_settings
    from app.services.security_policy import is_placeholder_secret

    raw_secret = (get_settings().web_secret or "").strip()
    if is_placeholder_secret(raw_secret):
        # Refuse to encrypt under a known/weak key — force ensure_web_secret first.
        from app.services.setup_wizard import ensure_web_secret

        raw_secret = ensure_web_secret()
    raw = raw_secret.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_secret(plain: str | None) -> str | None:
    text = (plain or "").strip()
    if not text:
        return None
    try:
        return _fernet().encrypt(text.encode("utf-8")).decode("ascii")
    except Exception:
        logger.exception("encrypt_secret failed")
        return None


def decrypt_secret(token: str | None) -> str | None:
    raw = (token or "").strip()
    if not raw:
        return None
    try:
        return _fernet().decrypt(raw.encode("ascii")).decode("utf-8")
    except Exception:
        logger.warning("decrypt_secret failed — secret unreadable")
        return None
