"""Rich Telegram text for settings (premium / custom emoji via entities).

Web edits store plain/HTML strings. Bot edits may pack text+entities as JSON so
custom emoji survive round-trip when re-sent with entities= (no HTML parse_mode).

Button labels (``btn_*``) also pack custom-emoji entities so keyboards can set
Bot API ``icon_custom_emoji_id`` (premium icon before the button text).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from aiogram.types import MessageEntity

logger = logging.getLogger(__name__)

_PACK_VERSION = 1
_RICH_PREFIX = "\x1eRICH1:"  # unlikely in normal settings HTML


def entities_to_json(entities: Sequence[MessageEntity] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in entities or []:
        typ = e.type
        typ_s = typ.value if hasattr(typ, "value") else str(typ)
        row: dict[str, Any] = {
            "type": typ_s,
            "offset": int(e.offset),
            "length": int(e.length),
        }
        if e.url:
            row["url"] = e.url
        if e.user and getattr(e.user, "id", None) is not None:
            row["user"] = {"id": int(e.user.id)}
        if e.language:
            row["language"] = e.language
        if e.custom_emoji_id:
            row["custom_emoji_id"] = str(e.custom_emoji_id)
        out.append(row)
    return out


def json_to_entities(rows: list[dict[str, Any]] | None) -> list[MessageEntity]:
    out: list[MessageEntity] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        try:
            kwargs: dict[str, Any] = {
                "type": str(row.get("type") or "italic"),
                "offset": int(row["offset"]),
                "length": int(row["length"]),
            }
            if row.get("url"):
                kwargs["url"] = str(row["url"])
            if row.get("language"):
                kwargs["language"] = str(row["language"])
            if row.get("custom_emoji_id"):
                kwargs["custom_emoji_id"] = str(row["custom_emoji_id"])
            out.append(MessageEntity(**kwargs))
        except Exception:
            logger.debug("skip bad entity row %r", row, exc_info=True)
    return out


def pack_rich_text(text: str, entities: Sequence[MessageEntity] | None = None) -> str:
    """Serialize text + entities for Setting.value. No entities → plain text."""
    body = text or ""
    ent = entities_to_json(entities)
    if not ent:
        return body
    payload = json.dumps(
        {"v": _PACK_VERSION, "text": body, "entities": ent},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return _RICH_PREFIX + payload


def unpack_rich_text(raw: str | None) -> tuple[str, list[MessageEntity] | None]:
    """Return (text, entities_or_None). Plain/HTML strings → entities None."""
    s = raw if raw is not None else ""
    if not s.startswith(_RICH_PREFIX):
        return s, None
    try:
        data = json.loads(s[len(_RICH_PREFIX) :])
        if not isinstance(data, dict) or int(data.get("v") or 0) != _PACK_VERSION:
            return s, None
        text = str(data.get("text") or "")
        ents = json_to_entities(data.get("entities") or [])
        return text, ents or None
    except Exception:
        logger.debug("rich unpack failed", exc_info=True)
        return s, None


def rich_plain_text(raw: str | None) -> str:
    """Display/edit surface for web textarea (entities stripped to plain text)."""
    text, _ = unpack_rich_text(raw)
    return text


def content_fingerprint(raw: str | None) -> str:
    """Stable hash of visible rules text (ignores entity packing wrapper)."""
    import hashlib

    text, _ = unpack_rich_text(raw)
    normalized = (text or "").replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def utf16_len(s: str) -> int:
    """Telegram entity offsets are UTF-16 code units."""
    return len((s or "").encode("utf-16-le")) // 2


def _utf16_slice(text: str, start: int, end: int) -> str:
    """Slice ``text`` by UTF-16 code-unit offsets (Telegram entity space)."""
    if not text or start >= end:
        return ""
    buf = (text or "").encode("utf-16-le")
    return buf[start * 2 : end * 2].decode("utf-16-le", errors="ignore")


def _entity_type_str(e: MessageEntity) -> str:
    typ = e.type
    return typ.value if hasattr(typ, "value") else str(typ)


def first_custom_emoji_id(entities: Sequence[MessageEntity] | None) -> str | None:
    for e in entities or []:
        if _entity_type_str(e) == "custom_emoji" and e.custom_emoji_id:
            return str(e.custom_emoji_id)
    return None


def strip_custom_emoji_spans(
    text: str, entities: Sequence[MessageEntity] | None
) -> str:
    """Remove custom-emoji glyphs so the icon is not duplicated in button text."""
    body = text or ""
    spans = [
        (int(e.offset), int(e.offset) + int(e.length))
        for e in entities or []
        if _entity_type_str(e) == "custom_emoji" and int(e.length) > 0
    ]
    if not spans:
        return body
    spans.sort()
    parts: list[str] = []
    cursor = 0
    total = utf16_len(body)
    for start, end in spans:
        start = max(0, min(start, total))
        end = max(start, min(end, total))
        if start > cursor:
            parts.append(_utf16_slice(body, cursor, start))
        cursor = max(cursor, end)
    if cursor < total:
        parts.append(_utf16_slice(body, cursor, total))
    # Collapse leftover double spaces from removed leading icons.
    return " ".join("".join(parts).split())


def is_button_label_key(key: str | None) -> bool:
    """Editable keyboard label settings (not btn_style_* color overrides)."""
    k = str(key or "")
    return k.startswith("btn_") and not k.startswith("btn_style_")


# Reply-action → btn_* setting key (icons look up via the same labels).
_ACTION_TO_BTN_KEY: dict[str, str] = {
    "home": "btn_menu_home",
    "referral": "btn_referral",
    "loy_referral": "btn_referral",
    "topup_card": "btn_pay_card",
    "topup_gateway": "btn_pay_gateway",
    "topup_psp": "btn_pay_psp",
    "topup_crypto": "btn_pay_crypto",
    "svc_renew": "btn_renew",
    "svc_link": "btn_sub_link",
}


def btn_setting_key_for_action(action: str | None) -> str | None:
    a = (action or "").strip()
    if not a:
        return None
    return _ACTION_TO_BTN_KEY.get(a) or f"btn_{a}"


def button_icon_custom_emoji_id(raw: str | None) -> str | None:
    """First packed custom_emoji id for Bot API icon_custom_emoji_id."""
    _, ents = unpack_rich_text(raw)
    return first_custom_emoji_id(ents)


def button_display_text(raw: str | None) -> str:
    """Plain button label: unpack + strip custom-emoji glyphs used as the icon."""
    text, ents = unpack_rich_text(raw)
    if ents and first_custom_emoji_id(ents):
        text = strip_custom_emoji_spans(text, ents)
    return text or ""


def button_icon_from_ui(ui: dict | None, *, label_key: str | None = None, action: str | None = None) -> str | None:
    if not ui:
        return None
    key = label_key or btn_setting_key_for_action(action)
    if not key:
        return None
    return button_icon_custom_emoji_id(ui.get(key))


def pack_setting_from_message(key: str, message: Any) -> str:
    """Pack bot-edited setting; preserve custom emoji for terms + button labels."""
    text = getattr(message, "text", None) or ""
    entities = getattr(message, "entities", None)
    if key in TERMS_RICH_KEYS or is_button_label_key(key):
        # Only pack when there is at least one custom_emoji (button icons / premium).
        if key in TERMS_RICH_KEYS:
            return pack_rich_text(text, entities)
        if first_custom_emoji_id(entities):
            return pack_rich_text(text, entities)
        return (text or "").strip()
    return (text or "").strip()


# Setting keys that preserve premium emoji when edited from Telegram.
TERMS_RICH_KEYS = frozenset(
    {
        "terms_entry_text",
        "terms_buy_user_text",
        "terms_buy_reseller_text",
        "terms_entry_btn",
        "terms_buy_user_btn",
        "terms_buy_reseller_btn",
    }
)


def _iter_rich_web_keys(values: dict) -> list[str]:
    keys = set(TERMS_RICH_KEYS)
    for k in values:
        if is_button_label_key(k):
            keys.add(k)
    return sorted(keys)


def prepare_settings_values_for_web(values: dict) -> dict:
    """Unpack rich keys to plain text for web textareas."""
    out = dict(values)
    for key in _iter_rich_web_keys(out):
        if key in out:
            out[key] = rich_plain_text(out.get(key))
    return out


def merge_rich_settings_on_save(existing: dict, payload: dict) -> dict:
    """Keep packed entities when web save did not change visible text."""
    keys = set(TERMS_RICH_KEYS)
    for k in list(payload.keys()) + list(existing.keys()):
        if is_button_label_key(k):
            keys.add(k)
    for key in keys:
        if key not in payload:
            continue
        new_plain = payload.get(key) or ""
        old_raw = existing.get(key)
        if rich_plain_text(old_raw) == new_plain:
            payload[key] = old_raw if old_raw is not None else new_plain
    return payload

