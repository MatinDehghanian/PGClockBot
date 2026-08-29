"""Card-auto provider webhook — HMAC-signed generic contract (Variza-class).

Not an SMS parser. Providers forward a signed JSON event; we match amount
(+ optional payment_id) and settle fail-closed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CardAutoEvent:
    external_ref: str
    amount: int
    payment_id: int | None = None
    card_last4: str | None = None
    raw: dict[str, Any] | None = None


def sign_payload(secret: str, body: bytes) -> str:
    key = (secret or "").encode("utf-8")
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def verify_signature(*, secret: str, body: bytes, signature: str) -> bool:
    if not secret or not signature:
        return False
    expected = sign_payload(secret, body)
    return hmac.compare_digest(expected, signature.strip().lower())


def parse_card_auto_event(payload: dict[str, Any]) -> CardAutoEvent:
    """Accept a small canonical JSON shape (provider-agnostic)."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    amount_raw = payload.get("amount")
    try:
        amount = int(amount_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("amount invalid") from exc
    if amount <= 0:
        raise ValueError("amount must be positive")
    ref = str(
        payload.get("external_ref")
        or payload.get("event_id")
        or payload.get("id")
        or ""
    ).strip()
    if not ref:
        raise ValueError("external_ref required")
    pid = payload.get("payment_id")
    payment_id = None
    if pid is not None and str(pid).strip() != "":
        try:
            payment_id = int(pid)
        except (TypeError, ValueError) as exc:
            raise ValueError("payment_id invalid") from exc
    last4 = payload.get("card_last4") or payload.get("pan")
    last4_s = str(last4).strip()[-4:] if last4 else None
    return CardAutoEvent(
        external_ref=ref[:128],
        amount=amount,
        payment_id=payment_id,
        card_last4=last4_s,
        raw=payload,
    )


def dumps_canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
