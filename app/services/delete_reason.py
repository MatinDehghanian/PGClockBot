"""Shared helpers for irreversible delete reason fields."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping


def extract_delete_reason(form: Mapping[str, Any] | MutableMapping[str, Any], *names: str) -> str:
    """Return the first non-empty trimmed reason from preferred form keys.

    Panel JS writes ``reason`` (or a custom ``data-confirm-reason-name``). The
    confirm modal textarea itself is named ``confirm_reason``; accept that too
    so a missed applyReason copy cannot block a delete the operator already
    confirmed.
    """
    keys = names or ("reason", "confirm_reason")
    for key in keys:
        raw = form.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def delete_reason_too_short(reason: str, *, minimum: int = 3) -> bool:
    return len((reason or "").strip()) < int(minimum)
