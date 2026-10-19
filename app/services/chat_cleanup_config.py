"""The «پاک‌سازی خودکار صفحهٔ ربات» switch, set per bot (platform or shop)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

KEY_ENABLED = "chat_cleanup_enabled"


def is_chat_cleanup_on(ui: Mapping[str, Any] | None) -> bool:
    """On unless this bot switched it off."""
    return str((ui or {}).get(KEY_ENABLED) or "").strip().lower() not in {"0", "false", "no", "off"}


def chat_cleanup_payload(form: Mapping[str, Any]) -> dict[str, str]:
    """The setting row a menu settings form saves; an unticked box posts nothing and means off."""
    return {KEY_ENABLED: "1" if str(form.get(KEY_ENABLED) or "") == "1" else "0"}
