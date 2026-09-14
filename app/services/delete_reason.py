"""Shared helpers for irreversible delete reason fields.

Pre-v10.1.14 panel deletes use a simple confirm dialog (no typed reason/phrase).
Server still accepts an optional reason for audit/notify; otherwise a default
is used so deletes never fail on an empty reason field.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, MutableMapping

DEFAULT_DELETE_REASON = "حذف از پنل"


def _iter_form_values(form: Mapping[str, Any] | MutableMapping[str, Any], key: str) -> Iterable[Any]:
    """Yield every value for ``key`` — Starlette/FormData ``.get()`` is last-wins."""
    getlist = getattr(form, "getlist", None)
    if callable(getlist):
        try:
            values = getlist(key)
        except Exception:
            values = None
        if values is not None:
            for raw in values:
                yield raw
            return
    multi_items = getattr(form, "multi_items", None)
    if callable(multi_items):
        try:
            for k, raw in multi_items():
                if k == key:
                    yield raw
            return
        except Exception:
            pass
    raw = form.get(key)
    if raw is not None:
        yield raw


def extract_delete_reason(form: Mapping[str, Any] | MutableMapping[str, Any], *names: str) -> str:
    """Return the first non-empty trimmed reason from preferred form keys."""
    keys = names or ("reason", "confirm_reason")
    for key in keys:
        for raw in _iter_form_values(form, key):
            if raw is None:
                continue
            text = str(raw).strip()
            if text:
                return text
    return ""


def resolve_delete_reason(
    form: Mapping[str, Any] | MutableMapping[str, Any],
    *names: str,
    default: str = DEFAULT_DELETE_REASON,
) -> str:
    """Optional reason for deletes — never blocks when empty."""
    text = extract_delete_reason(form, *names)
    return text or default


def delete_reason_too_short(reason: str, *, minimum: int = 3) -> bool:
    """Legacy helper kept for tests; panel deletes no longer enforce this."""
    return len((reason or "").strip()) < int(minimum)
