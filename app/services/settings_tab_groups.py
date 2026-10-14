"""Group the flat bot-settings tab list into a few labelled sections.

The bot settings page (platform owner and shop owner variants) lists many tabs.
Grouping only changes how the existing tab keys are presented; the keys, the
``?tab=`` URLs and the set of tabs each role receives are untouched. A tab that
no group claims falls into a trailing group so it can never disappear.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

FALLBACK_GROUP_KEY = "more"
FALLBACK_GROUP_LABEL = "سایر"

# (group key, label, tab keys in display order)
_GROUP_LAYOUT: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("look", "ظاهر و متن‌ها", ("welcome", "appearance", "messages", "buttons", "colors", "menu")),
    ("service", "سرویس و فروش", ("naming", "qr", "guides", "limits")),
    ("alerts", "اعلان‌ها", ("notifications", "daily_report")),
    ("connect", "اتصال و لینک‌ها", ("links", "bot")),
)


@dataclass(frozen=True, slots=True)
class SettingsTab:
    key: str
    label: str


@dataclass(frozen=True, slots=True)
class SettingsTabGroup:
    key: str
    label: str
    tabs: tuple[SettingsTab, ...]
    is_active: bool


def group_settings_tabs(
    tabs: Sequence[tuple[str, str]], active: str
) -> tuple[SettingsTabGroup, ...]:
    """Split ``tabs`` into groups, keeping only tabs the caller already holds."""
    available = {key: SettingsTab(key, label) for key, label in tabs}
    claimed: set[str] = set()
    groups: list[SettingsTabGroup] = []
    for group_key, label, keys in _GROUP_LAYOUT:
        members = tuple(available[key] for key in keys if key in available)
        claimed.update(tab.key for tab in members)
        if members:
            groups.append(_build_group(group_key, label, members, active))
    leftovers = tuple(tab for key, tab in available.items() if key not in claimed)
    if leftovers:
        groups.append(_build_group(FALLBACK_GROUP_KEY, FALLBACK_GROUP_LABEL, leftovers, active))
    return tuple(groups)


def _build_group(
    key: str, label: str, members: tuple[SettingsTab, ...], active: str
) -> SettingsTabGroup:
    return SettingsTabGroup(
        key=key,
        label=label,
        tabs=members,
        is_active=any(tab.key == active for tab in members),
    )
