"""Telegram Bot API appearance (name, about, short description, photo, commands)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.types import BotCommand, BufferedInputFile, InputProfilePhotoStatic

log = logging.getLogger(__name__)

NAME_MAX = 64
DESCRIPTION_MAX = 512
SHORT_DESCRIPTION_MAX = 120
CMD_DESC_MAX = 256

DEFAULT_CMD_START = "شروع / منو"
DEFAULT_CMD_HELP = "راهنما"

APPEARANCE_SETTING_KEYS = (
    "bot_tg_name",
    "bot_tg_description",
    "bot_tg_short_description",
    "bot_tg_photo",
    "bot_cmd_start",
    "bot_cmd_help",
)


@dataclass
class BotAppearance:
    name: str = ""
    username: str = ""
    description: str = ""
    short_description: str = ""
    cmd_start: str = DEFAULT_CMD_START
    cmd_help: str = DEFAULT_CMD_HELP
    photo_url: str = ""
    ok: bool = False
    error: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


def clip(text: str | None, limit: int) -> str:
    return (text or "").strip()[:limit]


def validate_appearance_form(
    *,
    name: str,
    description: str,
    short_description: str,
    cmd_start: str,
    cmd_help: str,
) -> str | None:
    if len(name) > NAME_MAX:
        return f"نام ربات حداکثر {NAME_MAX} کاراکتر است"
    # description = empty-chat text (متن وسط); short_description = profile caption (کپشن)
    if len(description) > DESCRIPTION_MAX:
        return f"متن وسط صفحه حداکثر {DESCRIPTION_MAX} کاراکتر است"
    if len(short_description) > SHORT_DESCRIPTION_MAX:
        return f"کپشن / درباره حداکثر {SHORT_DESCRIPTION_MAX} کاراکتر است"
    if len(cmd_start) > CMD_DESC_MAX or len(cmd_help) > CMD_DESC_MAX:
        return f"توضیح دستور حداکثر {CMD_DESC_MAX} کاراکتر است"
    if not (cmd_start or "").strip():
        return "توضیح دستور /start الزامی است"
    if not (cmd_help or "").strip():
        return "توضیح دستور /help الزامی است"
    return None


def _cmd_map(commands: list[Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in commands or []:
        try:
            out[str(c.command)] = str(c.description or "")
        except Exception:
            continue
    return out


async def fetch_appearance(token: str, *, local_photo: str = "") -> BotAppearance:
    token = (token or "").strip()
    if not token:
        return BotAppearance(error="توکن ربات تنظیم نشده", photo_url=local_photo)

    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        name_obj = await bot.get_my_name()
        desc_obj = await bot.get_my_description()
        short_obj = await bot.get_my_short_description()
        try:
            cmds = await bot.get_my_commands()
        except Exception:
            cmds = []
        cmap = _cmd_map(cmds)
        name = (getattr(name_obj, "name", None) or me.first_name or "").strip()
        return BotAppearance(
            name=name,
            username=(me.username or "").strip(),
            description=(getattr(desc_obj, "description", None) or "").strip(),
            short_description=(getattr(short_obj, "short_description", None) or "").strip(),
            cmd_start=cmap.get("start") or DEFAULT_CMD_START,
            cmd_help=cmap.get("help") or DEFAULT_CMD_HELP,
            photo_url=local_photo,
            ok=True,
        )
    except Exception as exc:
        log.warning("fetch_appearance failed: %s", exc)
        return BotAppearance(error=f"خواندن از تلگرام ناموفق: {exc}", photo_url=local_photo)
    finally:
        await bot.session.close()


async def apply_appearance(
    token: str,
    *,
    name: str,
    description: str,
    short_description: str,
    cmd_start: str = DEFAULT_CMD_START,
    cmd_help: str = DEFAULT_CMD_HELP,
    photo_bytes: bytes | None = None,
    photo_filename: str = "photo.jpg",
    remove_photo: bool = False,
) -> BotAppearance:
    """Push appearance fields to Telegram Bot API."""
    token = (token or "").strip()
    if not token:
        return BotAppearance(error="توکن ربات تنظیم نشده")

    name = clip(name, NAME_MAX)
    description = clip(description, DESCRIPTION_MAX)
    short_description = clip(short_description, SHORT_DESCRIPTION_MAX)
    cmd_start = clip(cmd_start, CMD_DESC_MAX) or DEFAULT_CMD_START
    cmd_help = clip(cmd_help, CMD_DESC_MAX) or DEFAULT_CMD_HELP

    err = validate_appearance_form(
        name=name,
        description=description,
        short_description=short_description,
        cmd_start=cmd_start,
        cmd_help=cmd_help,
    )
    if err:
        return BotAppearance(error=err)

    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        await bot.set_my_name(name=name)
        await bot.set_my_description(description=description)
        await bot.set_my_short_description(short_description=short_description)
        await bot.set_my_commands(
            [
                BotCommand(command="start", description=cmd_start),
                BotCommand(command="help", description=cmd_help),
            ]
        )
        if remove_photo and not photo_bytes:
            try:
                await bot.remove_my_profile_photo()
            except Exception as exc:
                log.warning("remove_my_profile_photo: %s", exc)
                return BotAppearance(error=f"حذف عکس پروفایل ناموفق: {exc}")
        if photo_bytes:
            fname = (photo_filename or "photo.jpg").lower()
            if not fname.endswith((".jpg", ".jpeg")):
                fname = Path(fname).stem + ".jpg"
            photo = InputProfilePhotoStatic(
                photo=BufferedInputFile(photo_bytes, filename=fname)
            )
            try:
                await bot.set_my_profile_photo(photo=photo)
            except Exception as exc:
                log.warning("set_my_profile_photo: %s", exc)
                return BotAppearance(
                    error=f"آپلود عکس پروفایل ناموفق (فقط JPG): {exc}",
                    name=name,
                    username=(me.username or "").strip(),
                    description=description,
                    short_description=short_description,
                    cmd_start=cmd_start,
                    cmd_help=cmd_help,
                )

        return BotAppearance(
            name=name,
            username=(me.username or "").strip(),
            description=description,
            short_description=short_description,
            cmd_start=cmd_start,
            cmd_help=cmd_help,
            ok=True,
        )
    except Exception as exc:
        log.warning("apply_appearance failed: %s", exc)
        return BotAppearance(error=f"اعمال در تلگرام ناموفق: {exc}")
    finally:
        await bot.session.close()


def appearance_to_form_dict(app: BotAppearance, *, local_photo: str = "") -> dict[str, str]:
    return {
        "bot_tg_name": app.name or "",
        "bot_tg_description": app.description or "",
        "bot_tg_short_description": app.short_description or "",
        "bot_tg_photo": local_photo or app.photo_url or "",
        "bot_cmd_start": app.cmd_start or DEFAULT_CMD_START,
        "bot_cmd_help": app.cmd_help or DEFAULT_CMD_HELP,
        "bot_username": app.username or "",
    }


async def load_appearance_context(
    session,
    *,
    token: str,
    reseller_id: int | None = None,
    fallback_username: str = "",
) -> dict[str, Any]:
    """Build template context for appearance tab (Telegram + local cache)."""
    from app.services.users import get_all_settings

    values = await get_all_settings(session, reseller_id=reseller_id)
    local_photo = (values.get("bot_tg_photo") or "").strip()
    fetched = await fetch_appearance(token, local_photo=local_photo)
    if fetched.ok:
        form = appearance_to_form_dict(fetched, local_photo=local_photo)
        # Prefer Telegram values; keep local photo for panel preview
        return {
            "appearance": form,
            "appearance_sync_ok": True,
            "appearance_sync_err": "",
        }
    # Fallback to cached settings when Telegram unreachable
    form = {
        "bot_tg_name": values.get("bot_tg_name") or "",
        "bot_tg_description": values.get("bot_tg_description") or "",
        "bot_tg_short_description": values.get("bot_tg_short_description") or "",
        "bot_tg_photo": local_photo,
        "bot_cmd_start": values.get("bot_cmd_start") or DEFAULT_CMD_START,
        "bot_cmd_help": values.get("bot_cmd_help") or DEFAULT_CMD_HELP,
        "bot_username": fallback_username or "",
    }
    return {
        "appearance": form,
        "appearance_sync_ok": False,
        "appearance_sync_err": fetched.error or "خواندن از تلگرام ناموفق",
    }


async def save_appearance_from_form(
    session,
    form,
    *,
    token: str,
    reseller_id: int | None = None,
    upload_prefix: str = "",
) -> tuple[bool, str]:
    """Validate form, push to Telegram, persist local cache. Returns (ok, message)."""
    import uuid

    from starlette.datastructures import UploadFile

    from app.config import DATA_DIR
    from app.services.users import set_setting

    name = clip(str(form.get("bot_tg_name") or ""), NAME_MAX)
    description = clip(str(form.get("bot_tg_description") or ""), DESCRIPTION_MAX)
    short_description = clip(str(form.get("bot_tg_short_description") or ""), SHORT_DESCRIPTION_MAX)
    cmd_start = clip(str(form.get("bot_cmd_start") or ""), CMD_DESC_MAX) or DEFAULT_CMD_START
    cmd_help = clip(str(form.get("bot_cmd_help") or ""), CMD_DESC_MAX) or DEFAULT_CMD_HELP
    remove_photo = str(form.get("bot_tg_photo_clear") or "") in {"1", "on", "true", "yes"}

    err = validate_appearance_form(
        name=name,
        description=description,
        short_description=short_description,
        cmd_start=cmd_start,
        cmd_help=cmd_help,
    )
    if err:
        return False, err

    photo_bytes: bytes | None = None
    photo_filename = "photo.jpg"
    upload = form.get("bot_tg_photo")
    if isinstance(upload, UploadFile) and upload.filename:
        fname = upload.filename.lower()
        ext = Path(fname).suffix
        if ext not in {".jpg", ".jpeg"}:
            return False, "عکس پروفایل باید JPG باشد"
        content = await upload.read()
        if content:
            photo_bytes = content
            photo_filename = Path(fname).name
            remove_photo = False

    result = await apply_appearance(
        token,
        name=name,
        description=description,
        short_description=short_description,
        cmd_start=cmd_start,
        cmd_help=cmd_help,
        photo_bytes=photo_bytes,
        photo_filename=photo_filename,
        remove_photo=remove_photo,
    )
    if not result.ok:
        return False, result.error or "اعمال در تلگرام ناموفق"

    await set_setting(session, "bot_tg_name", name, reseller_id=reseller_id)
    await set_setting(session, "bot_tg_description", description, reseller_id=reseller_id)
    await set_setting(
        session, "bot_tg_short_description", short_description, reseller_id=reseller_id
    )
    await set_setting(session, "bot_cmd_start", cmd_start, reseller_id=reseller_id)
    await set_setting(session, "bot_cmd_help", cmd_help, reseller_id=reseller_id)

    if remove_photo and not photo_bytes:
        await set_setting(session, "bot_tg_photo", "", reseller_id=reseller_id)
    elif photo_bytes:
        uploads = DATA_DIR / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        prefix = upload_prefix or ("r" + str(reseller_id) if reseller_id else "main")
        dest_name = f"{prefix}_bot_tg_photo_{uuid.uuid4().hex[:10]}.jpg"
        dest = uploads / dest_name
        dest.write_bytes(photo_bytes)
        await set_setting(session, "bot_tg_photo", f"uploads/{dest_name}", reseller_id=reseller_id)

    # Drop legacy welcome/middle photo setting if still present
    await set_setting(session, "welcome_image", "", reseller_id=reseller_id)

    return True, "ظاهر ربات در تلگرام اعمال شد"
