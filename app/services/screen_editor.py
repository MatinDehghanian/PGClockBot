"""Rules for the in-menu screen editor (edit mode).

Edit mode is switched on per person and per bot and stays on until
``EDIT_MODE_MINUTES`` pass without a saved change, and only while the platform
owner has enabled the feature (``SCREEN_EDITOR_SETTING``, off by default).
The platform owner may edit customer and admin menus in platform settings; a
shop owner may edit customer and reseller menus in their own shop's settings.
Every save re-checks what the actor may change, independent of which buttons
were shown.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.button_color_editor import PLATFORM_SCOPE
from app.services.rich_text import is_button_label_key
from app.services.screen_titles import has_title, title_setting_key, validate_screen_title
from app.services.settings_button_labels import all_btn_field_keys
from app.services.users import DEFAULT_SETTINGS, get_all_settings, on, set_setting

SCREEN_EDITOR_SETTING = "screen_editor_enabled"
EDIT_MODE_MINUTES = 30
# Edit mode is only ever switched on by owners, so this bound is never reached
# in practice; it keeps the table from growing without limit.
MAX_ACTIVE_EDITORS = 1000
LABEL_MAX_LENGTH = 64

OWNER_AUDIENCES = frozenset({"customer", "admin"})
SHOP_AUDIENCES = frozenset({"customer", "reseller"})


@dataclass(frozen=True, slots=True)
class EditorActor:
    """Who edits: the platform owner (``shop_id`` None) or one shop's owner."""

    user_id: int
    shop_id: int | None

    @property
    def for_reseller(self) -> bool:
        return self.shop_id is not None

    @property
    def settings_scope(self) -> int:
        return self.shop_id if self.shop_id is not None else PLATFORM_SCOPE

    @property
    def audiences(self) -> frozenset[str]:
        return SHOP_AUDIENCES if self.for_reseller else OWNER_AUDIENCES


class EditModeStore:
    """Per-person edit-mode switches with an expiry, keyed by (user, shop)."""

    def __init__(self, *, minutes: int = EDIT_MODE_MINUTES, capacity: int = MAX_ACTIVE_EDITORS) -> None:
        self._seconds = minutes * 60
        self._capacity = capacity
        self._until: dict[tuple[int, int], float] = {}

    def activate(self, actor: EditorActor, *, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        self._drop_expired(now)
        if len(self._until) >= self._capacity:
            self._until.pop(min(self._until, key=self._until.__getitem__))
        expires = now + self._seconds
        self._until[self._key(actor)] = expires
        return expires

    def extend(self, actor: EditorActor, *, now: float | None = None) -> bool:
        """Restart the window of a switch that is still on; an expired one stays off."""
        now = time.monotonic() if now is None else now
        if not self.is_active(actor, now=now):
            return False
        self._until[self._key(actor)] = now + self._seconds
        return True

    def deactivate(self, actor: EditorActor) -> None:
        self._until.pop(self._key(actor), None)

    def is_active(self, actor: EditorActor, *, now: float | None = None) -> bool:
        expires = self._until.get(self._key(actor))
        if expires is None:
            return False
        if (time.monotonic() if now is None else now) >= expires:
            self._until.pop(self._key(actor), None)
            return False
        return True

    def minutes_left(self, actor: EditorActor, *, now: float | None = None) -> int:
        expires = self._until.get(self._key(actor))
        now = time.monotonic() if now is None else now
        if expires is None or now >= expires:
            return 0
        return max(1, math.ceil((expires - now) / 60))

    def _drop_expired(self, now: float) -> None:
        for key in [key for key, expires in self._until.items() if now >= expires]:
            del self._until[key]

    @staticmethod
    def _key(actor: EditorActor) -> tuple[int, int]:
        return actor.user_id, actor.shop_id or 0


edit_mode_store = EditModeStore()


async def is_editor_enabled(session: AsyncSession) -> bool:
    """The platform-wide switch; shops follow the platform owner's choice."""
    platform = await get_all_settings(session, reseller_id=PLATFORM_SCOPE)
    return on(platform.get(SCREEN_EDITOR_SETTING, DEFAULT_SETTINGS.get(SCREEN_EDITOR_SETTING, "0")))


async def set_editor_enabled(session: AsyncSession, enabled: bool) -> None:
    await set_setting(session, SCREEN_EDITOR_SETTING, "1" if enabled else "0", reseller_id=PLATFORM_SCOPE)


def can_edit_label(actor: EditorActor, label_key: str | None) -> bool:
    if not label_key or not is_button_label_key(label_key) or label_key not in DEFAULT_SETTINGS:
        return False
    if actor.for_reseller:
        return label_key in all_btn_field_keys(include_platform=False)
    return True


def validate_button_label(text: str, *, other_labels: list[str], reserved: list[str]) -> str:
    """Return the cleaned label or raise ValueError with a message for the editor."""
    label = " ".join((text or "").split())
    if not label:
        raise ValueError("متن دکمه نمی‌تواند خالی باشد.")
    if "\n" in (text or "").strip():
        raise ValueError("متن دکمه باید یک خط باشد.")
    if len(label) > LABEL_MAX_LENGTH:
        raise ValueError(f"متن دکمه حداکثر {LABEL_MAX_LENGTH} کاراکتر است.")
    if label in reserved:
        raise ValueError("این متن برای دکمه‌های ناوبری رزرو است.")
    if label in other_labels:
        raise ValueError("این متن روی دکمهٔ دیگری از همین منو هست.")
    return label


async def save_button_label(
    session: AsyncSession, actor: EditorActor, *, label_key: str, stored_value: str
) -> None:
    """Persist a validated label in the actor's own settings (stale-label aliases included)."""
    if not can_edit_label(actor, label_key):
        raise ValueError("متن این دکمه قابل ویرایش نیست.")
    await set_setting(session, label_key, stored_value, reseller_id=actor.settings_scope)


async def save_screen_title(
    session: AsyncSession, actor: EditorActor, *, screen_id: str, audience: str, text: str
) -> str:
    """Validate and persist a menu title in the actor's own settings; return the stored title."""
    if not has_title(screen_id) or audience not in actor.audiences:
        raise ValueError("تیتر این منو قابل ویرایش نیست.")
    title = validate_screen_title(text)
    await set_setting(session, title_setting_key(screen_id), title, reseller_id=actor.settings_scope)
    return title
