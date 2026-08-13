"""Encrypt small secrets at rest (reseller PG passwords) using WEB_SECRET.

WEB_SECRET is also the root key for signing session cookies (see
``get_signer()`` in ``app.api.app``, via itsdangerous with its own
``salt="pgclock-session"``). To avoid reusing the exact same raw key
material across two unrelated cryptographic primitives (HMAC signing vs.
Fernet/AES encryption), the Fernet key used here is derived from
WEB_SECRET through HKDF with a dedicated, constant ``info`` label — a
domain-separated subkey rather than the root secret itself.

Backward compatibility: secrets encrypted before this change used a plain
``sha256(WEB_SECRET)`` Fernet key with no domain separation. That legacy key
is kept as a decrypt-only fallback so existing ciphertext (e.g. resellers'
encrypted PasarGuard passwords already stored in the DB) keeps working with
zero migration — new encryptions always use the HKDF-derived key.
"""

from __future__ import annotations

import base64
import hashlib
import logging

logger = logging.getLogger(__name__)

_HKDF_INFO = b"pgclockbot:secret-box:v1"


def _root_secret() -> bytes:
    from app.config import get_settings
    from app.services.security_policy import is_placeholder_secret

    raw_secret = (get_settings().web_secret or "").strip()
    if is_placeholder_secret(raw_secret):
        # Refuse to encrypt under a known/weak key — force ensure_web_secret first.
        from app.services.setup_wizard import ensure_web_secret

        raw_secret = ensure_web_secret()
    return raw_secret.encode("utf-8")


def _hkdf_fernet_key(secret: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(secret)
    return base64.urlsafe_b64encode(derived)


def _legacy_fernet_key(secret: bytes) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret).digest())


def _fernet_keys() -> list[bytes]:
    """Primary (domain-separated) key first, then the legacy key as decrypt fallback."""
    secret = _root_secret()
    return [_hkdf_fernet_key(secret), _legacy_fernet_key(secret)]


def _fernet(key: bytes):
    from cryptography.fernet import Fernet

    return Fernet(key)


def encrypt_secret(plain: str | None) -> str | None:
    text = (plain or "").strip()
    if not text:
        return None
    try:
        key = _fernet_keys()[0]
        return _fernet(key).encrypt(text.encode("utf-8")).decode("ascii")
    except Exception:
        logger.exception("encrypt_secret failed")
        return None


def decrypt_secret(token: str | None) -> str | None:
    raw = (token or "").strip()
    if not raw:
        return None
    for key in _fernet_keys():
        try:
            return _fernet(key).decrypt(raw.encode("ascii")).decode("utf-8")
        except Exception:
            continue
    logger.warning("decrypt_secret failed — secret unreadable")
    return None
