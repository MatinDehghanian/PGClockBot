"""Connection guides — admin-editable inline buttons for users / resellers.

Stored as JSON in settings.connection_guides (shop-scoped via reseller settings).
Each item: title, body text, audience, button style, optional deep-link flag.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.button_styles import parse_item_button_style_raw
from app.services.users import get_setting, set_setting

SETTING_KEY = "connection_guides"
AUDIENCES = frozenset({"user", "reseller"})

_STYLE_UNSET = object()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _sanitize_title(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    s = re.sub(r'[<>"\'`]', "", s)
    return s.strip()[:64]


def _sanitize_body(raw: str) -> str:
    # Keep HTML-ish rich text from admin; cap length for Telegram safety.
    return (raw or "").strip()[:4000]


def parse_connection_guides(raw: str | None) -> list[dict[str, Any]]:
    if not (raw or "").strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        title = _sanitize_title(str(item.get("title") or ""))
        body = _sanitize_body(str(item.get("body") or item.get("text") or ""))
        audience = str(item.get("audience") or "user").strip().lower()
        if audience not in AUDIENCES:
            audience = "user"
        enabled = item.get("enabled")
        if enabled is None:
            enabled = item.get("active", True)
        try:
            sort = int(item.get("sort", i))
        except (TypeError, ValueError):
            sort = i
        deep_link = bool(item.get("deep_link") or item.get("deep_link_enabled"))
        gid = str(item.get("id") or "").strip() or _new_id()
        style_raw = item.get("style", item.get("button_style", _STYLE_UNSET))
        # Accept legacy nested {"button_style": "..."} from earlier drafts.
        if isinstance(style_raw, dict):
            style_raw = style_raw.get("button_style", _STYLE_UNSET)
        style = (
            parse_item_button_style_raw(style_raw)
            if style_raw is not _STYLE_UNSET
            else None
        )
        entry: dict[str, Any] = {
            "id": gid[:32],
            "title": title,
            "body": body,
            "audience": audience,
            "enabled": bool(enabled),
            "sort": sort,
            "deep_link": deep_link,
        }
        if style is not None:
            # Store plain Telegram style token (""|primary|success|danger), not a nested dict.
            entry["style"] = style
        if title or body:
            out.append(entry)
    out.sort(key=lambda x: (int(x.get("sort") or 0), str(x.get("title") or "")))
    return out


def serialize_connection_guides(items: list[dict[str, Any]] | None) -> str:
    clean = parse_connection_guides(json.dumps(items or []))
    return json.dumps(clean, ensure_ascii=False)


def default_connection_guides() -> list[dict[str, Any]]:
    """Persian starter guides — admin can edit/remove."""
    return [
        {
            "id": "v2box",
            "title": "V2Box",
            "body": (
                "۱) اپ V2Box را نصب کنید.\n"
                "۲) دکمه افزودن اشتراک / + را بزنید.\n"
                "۳) لینک اشتراک را وارد کنید یا از دکمه «باز کردن لینک» استفاده کنید.\n"
                "۴) اتصال را فعال کنید."
            ),
            "audience": "user",
            "enabled": True,
            "sort": 0,
            "deep_link": True,
            "style": "primary",
        },
        {
            "id": "streisand",
            "title": "Streisand",
            "body": (
                "۱) اپ Streisand را نصب کنید.\n"
                "۲) اشتراک را از طریق لینک اضافه کنید.\n"
                "۳) پروفایل را انتخاب و وصل شوید."
            ),
            "audience": "user",
            "enabled": True,
            "sort": 1,
            "deep_link": True,
            "style": "success",
        },
        {
            "id": "reseller_panel",
            "title": "اتصال به پنل نماینده",
            "body": (
                "۱) لینک پنل نمایندگی را در مرورگر باز کنید.\n"
                "۲) با نام کاربری و رمزی که برایتان ارسال شده وارد شوید.\n"
                "۳) از بخش سرویس‌ها اشتراک بسازید یا وضعیت را ببینید."
            ),
            "audience": "reseller",
            "enabled": True,
            "sort": 0,
            "deep_link": False,
            "style": "primary",
        },
    ]


async def get_connection_guides(
    session: AsyncSession,
    *,
    reseller_id: int | None = None,
) -> list[dict[str, Any]]:
    raw = await get_setting(session, SETTING_KEY, "", reseller_id=reseller_id)
    items = parse_connection_guides(raw)
    if items:
        return items
    # Seed defaults into memory only — persist on first admin save.
    return default_connection_guides()


async def save_connection_guides(
    session: AsyncSession,
    items: list[dict[str, Any]],
    *,
    reseller_id: int | None = None,
    commit: bool = True,
) -> list[dict[str, Any]]:
    clean = parse_connection_guides(json.dumps(items or []))
    await set_setting(
        session,
        SETTING_KEY,
        serialize_connection_guides(clean),
        reseller_id=reseller_id,
        commit=commit,
    )
    return clean


def guides_for_audience(
    items: list[dict[str, Any]],
    audience: str,
    *,
    enabled_only: bool = True,
) -> list[dict[str, Any]]:
    aud = "reseller" if audience == "reseller" else "user"
    out = []
    for g in items:
        if str(g.get("audience") or "user") != aud:
            continue
        if enabled_only and not g.get("enabled", True):
            continue
        out.append(g)
    return out


def guide_import_url(sub_url: str | None) -> str | None:
    """Telegram url-button target — only http(s) subscription links are safe to open."""
    url = (sub_url or "").strip()
    if url.startswith(("http://", "https://")):
        return url
    return None
