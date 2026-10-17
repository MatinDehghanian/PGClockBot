"""Editable titles at the top of the bot's main menus.

Each title is a plain one-line setting (``screen_title_<screen>``) whose
default is the text the menu always showed. Titles never contain ``<``, ``>``
or ``&`` (validated on save), so a title is safe both inside HTML messages
and in entity-formatted messages that are sent without a parse mode.
"""

from __future__ import annotations

import html
import re

TITLE_MAX_LENGTH = 64
_FORBIDDEN_CHARS = frozenset("<>&")
# A leading run of emoji/symbols stays outside <b>, as the menus always rendered it.
_ICON_PREFIX_RE = re.compile(r"^([^\w\s]+(?:\s+[^\w\s]+)*)\s+(\S.*)$")

SCREEN_TITLE_DEFAULTS: dict[str, str] = {
    "c.wallet": "👛 کیف پول",
    "c.support": "🎧 پشتیبانی",
    "c.loyalty": "⭐ باشگاه مشتریان",
    "c.services": "📦 سرویس‌های شما",
    "a.home": "🛠 پنل ادمین",
    "a.ops": "🗓 عملیات روزانه",
    "a.people": "👤 افراد",
    "a.product": "📦 محصول و PG",
    "a.marketing": "🎯 بازاریابی",
    "a.system": "🛠 سیستم",
    "a.pg": "🖥 عملیات پاسارگارد",
    "a.loyalty": "⭐ باشگاه مشتریان",
    "a.users": "👥 کاربران بات",
    "a.resellers": "🤝 نمایندگان",
    "a.settings": "⚙️ تنظیمات سریع",
    "a.backup": "💾 بکاپ / ریستور",
    "a.broadcast": "📢 پیام گروهی",
    "a.plans": "💎 پلن‌ها",
    "a.plans.users": "👥 پلن‌های کاربران",
    "a.plans.resellers": "🤝 پلن‌های نمایندگان",
    "r.home": "🤝 پنل نماینده",
    "r.settings": "⚙️ تنظیمات سریع فروشگاه",
    "r.plans": "💎 پلن‌های فروش",
}


def title_setting_key(screen_id: str) -> str:
    return "screen_title_" + screen_id.replace(".", "_")


def title_setting_defaults() -> dict[str, str]:
    return {title_setting_key(sid): title for sid, title in SCREEN_TITLE_DEFAULTS.items()}


def has_title(screen_id: str) -> bool:
    return screen_id in SCREEN_TITLE_DEFAULTS


def screen_title(ui: dict[str, str] | None, screen_id: str) -> str:
    """The title as plain text: the stored setting, or the default when it is blank."""
    stored = ((ui or {}).get(title_setting_key(screen_id)) or "").strip()
    return stored or SCREEN_TITLE_DEFAULTS[screen_id]


def screen_heading(ui: dict[str, str] | None, screen_id: str) -> str:
    """HTML heading in the menus' «🛠 <b>پنل ادمین</b>» shape."""
    title = screen_title(ui, screen_id)
    match = _ICON_PREFIX_RE.match(title)
    if match is None:
        return f"<b>{html.escape(title, quote=False)}</b>"
    icon, words = match.groups()
    return f"{html.escape(icon, quote=False)} <b>{html.escape(words, quote=False)}</b>"


def validate_screen_title(text: str) -> str:
    """Return the cleaned title or raise ValueError with a message for the editor."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("تیتر نمی‌تواند خالی باشد.")
    if "\n" in raw:
        raise ValueError("تیتر باید یک خط باشد.")
    title = " ".join(raw.split())
    if len(title) > TITLE_MAX_LENGTH:
        raise ValueError(f"تیتر حداکثر {TITLE_MAX_LENGTH} کاراکتر است.")
    if _FORBIDDEN_CHARS & set(title):
        raise ValueError("تیتر نمی‌تواند < یا > یا & داشته باشد.")
    return title
