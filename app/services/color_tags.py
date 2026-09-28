"""Staff color tags for bot users / resellers — fixed palette, scoped writes.

Security:
- Tags are staff-only metadata on ``BotUser.color_tag``.
- Callers must enforce shop / descendant scope before mutate.
- Unknown tokens normalize to ``None`` (clear); never accept free-form colors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ColorTag:
    key: str
    title_fa: str
    hex: str


# Compact fixed palette — matches panel status tones, not Telegram button styles.
COLOR_TAGS: tuple[ColorTag, ...] = (
    ColorTag("red", "قرمز", "#ef4444"),
    ColorTag("orange", "نارنجی", "#f97316"),
    ColorTag("amber", "کهربایی", "#eab308"),
    ColorTag("green", "سبز", "#22c55e"),
    ColorTag("blue", "آبی", "#3b82f6"),
    ColorTag("violet", "بنفش", "#8b5cf6"),
    ColorTag("pink", "صورتی", "#ec4899"),
    ColorTag("slate", "خاکستری", "#64748b"),
)

_BY_KEY = {t.key: t for t in COLOR_TAGS}
VALID_COLOR_KEYS: frozenset[str] = frozenset(_BY_KEY)
# Query token for "no tag" filter (never stored on the row).
FILTER_NONE = "_none"


def normalize_color_tag(raw: str | None) -> str | None:
    """Return a valid palette key, or ``None`` to clear / unset."""
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if not key or key in {"0", "none", "clear", "off", "-", FILTER_NONE}:
        return None
    return key if key in _BY_KEY else None


def normalize_color_filter(raw: str | None) -> str | None:
    """Whitelist list-filter token: palette key, ``_none``, or ``None`` (all)."""
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if not key or key == "all":
        return None
    if key == FILTER_NONE:
        return FILTER_NONE
    return key if key in _BY_KEY else None


def color_tag_meta(key: str | None) -> ColorTag | None:
    if not key:
        return None
    return _BY_KEY.get(str(key).strip().lower())


def color_tags_for_ui() -> list[dict[str, str]]:
    return [
        {"key": t.key, "title_fa": t.title_fa, "hex": t.hex}
        for t in COLOR_TAGS
    ]


def apply_color_tag(user: Any, raw: str | None) -> str | None:
    """Set ``user.color_tag`` from form input; returns stored value (or None)."""
    value = normalize_color_tag(raw)
    user.color_tag = value
    return value
