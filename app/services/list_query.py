"""Shared list helpers: case-insensitive substring search + sort keys."""

from __future__ import annotations

from typing import Any, Callable, Iterable


def normalize_search_q(raw: str | None) -> str:
    return str(raw or "").strip()


def text_matches(*parts: Any, needle: str) -> bool:
    """True when needle is empty or appears in any part (case-insensitive, substring)."""
    q = normalize_search_q(needle)
    if not q:
        return True
    needle_cf = q.casefold()
    for part in parts:
        if part is None:
            continue
        if needle_cf in str(part).casefold():
            return True
    return False


def filter_by_search(
    rows: Iterable[Any],
    needle: str,
    extractor: Callable[[Any], Iterable[Any]],
) -> list[Any]:
    q = normalize_search_q(needle)
    if not q:
        return list(rows)
    out: list[Any] = []
    for row in rows:
        if text_matches(*extractor(row), needle=q):
            out.append(row)
    return out


def ilike_pattern(q: str) -> str:
    """SQL ILIKE / LIKE pattern for substring match (caller must use bind param)."""
    # Escape LIKE wildcards in user input
    cleaned = normalize_search_q(q).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{cleaned}%"
