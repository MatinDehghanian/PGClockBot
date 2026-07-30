"""Shared bot authorization helpers."""

from __future__ import annotations

from app.config import get_settings
from app.db.models import BotUser, Role


def is_platform_admin(user: BotUser) -> bool:
    """True when the Telegram user is a platform admin (role or ADMIN_IDS)."""
    return user.role == Role.ADMIN.value or user.telegram_id in get_settings().admin_ids
