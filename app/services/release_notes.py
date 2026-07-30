"""Persian release notes shown on the panel update page."""

from __future__ import annotations

import ast
import logging
import time
from typing import Any

import httpx

from app.services.updates import is_newer, local_version
from app.version import GITHUB_RELEASE_NOTES_URL

logger = logging.getLogger(__name__)

# Newest first. Keep short and scannable — UI shows only the latest version block.
RELEASE_NOTES_FA: dict[str, list[str]] = {
    "1.9.0": [
        "رفع پایه‌ای زوم موبایل روی فیلدها (حداقل ۱۶px + گارد JS/تست)",
        "وسط‌چین شدن آیکن چشم رمز؛ عدم پر شدن خودکار یوزرنیم با admin",
        "جداسازی مثال داخل فیلد از راهنمای زیر فیلد در تنظیمات و کاربران",
    ],
    "1.8.6": [
        "بازتراحی امنیت وب‌پنل: تغییر یوزر و رمز در یک فرم",
        "رفع همپوشانی دکمه‌های ذخیره/بکاپ در تنظیمات و باکس آپلود با +",
        "ریستور بکاپ با مودال تأیید؛ تب فعال و دکمه ستاره نارنجی؛ کپی‌شد سبز",
        "ادغام حالت چیدمان منو؛ محدودیت یوزرنیم پاسارگارد و ارور داخل مودال",
    ],
    "1.8.5": [
        "چنج‌لاگ صفحه آپدیت برای نسخهٔ هدف (نسخهٔ جدید) نمایش داده می‌شود",
    ],
    "1.8.4": [
        "بازگشت فوتر پنل (کپی‌رایت، GitHub، دکمه ستاره) در دسکتاپ و موبایل",
        "شتاب ربات: کش تنظیمات، کش عضویت فورس‌جوین، WAL اسکیولایت و حذف queryهای تکراری",
    ],
    "1.8.3": [
        "مدیریت کاربران پاسارگارد در ربات: لیست ۱۰تایی، صفحه قبل/بعد، جستجو",
        "ساخت/ویرایش/حذف/لینک ساب و اکشن‌های پنل از داخل ربات",
    ],
    "1.8.2": [
        "رفع فورس‌جوین روی /start و قفل‌نشدن در خطای کانال",
        "جلوگیری از پرداخت تکراری کیف‌پول و تأیید مبلغ استارز",
        "عدم بازنشانی رمز پنل از .env در هر ری‌استارت",
        "کنترل دسترسی تمپلیت/گروه برای نماینده و نوتیف از ربات فروشگاه",
    ],
    "1.8.1": [
        "چنج‌لاگ فقط تغییرات آخرین نسخه",
        "حذف دکمه گیت‌هاب و پاک‌سازی وضعیت از صفحه آپدیت",
        "روش جایگزین با آدرس اسکریپت نصب و گزینه Update",
    ],
    "1.8.0": [
        "رنگ دکمه نمای کلی در باکس‌های داشبورد هماهنگ با رنگ همان باکس",
    ],
    "1.7.47": [
        "نمایش پایدار چنج‌لاگ در صفحه آپدیت",
        "تایتل باکس سایدبار: وب پنل",
        "حذف دکمه بروزرسانی دستی داشبورد",
        "هم‌ارتفاع شدن باکس جستجو و دکمه جستجو",
    ],
    "1.7.46": [
        "لینک اشتراک کاربران پاسارگارد با مودال و دریافت از سرور",
        "بک‌دراپ مودال مات (بدون سرمه ای)",
        "جلوگیری از زوم صفحه هنگام تایپ در موبایل",
        "یکدست‌سازی فاصله‌ها و تایتل‌های سایدبار",
    ],
    "1.7.45": [
        "چنج‌لاگ فارسی در صفحه آپدیت",
        "تنظیمات وب‌پنل یک‌جا با تب (زیر داشبورد)",
        "اصلاح ساخت کاربر پاسارگارد و پیام خطای واضح‌تر",
        "باکس CPU/RAM در موبایل مربعی؛ در دسکتاپ عنوان روبه‌روی دایره",
    ],
    "1.7.44": [
        "مودال‌ها وسط صفحه (موبایل و دسکتاپ)",
        "لینک ساب و ویرایش در منوی کاربران پاسارگارد",
        "مدت کاربر بر اساس روز؛ اتصال مجدد نودها",
        "بهبود سرعت پنل (کش نقش، واکشی موازی، panel.js)",
    ],
    "1.7.43": [
        "جدا شدن تنظیمات وب‌پنل از تنظیمات ربات",
        "چیدمان داشبورد و وضعیت اتصال با تگ متصل/قطع",
        "پس‌زمینه یکدست باکس‌های ربات و پاسارگارد",
    ],
    "1.7.42": [
        "گیج CPU/RAM تمام‌عرض در دسکتاپ",
        "پنل ربات و پاسارگارد در یک ستون",
    ],
    "1.7.41": [
        "شروع وب‌اپ روی داشبورد کلی",
        "پاک‌سازی مسیر آپدیت و بهینه‌سازی صفحه خانه",
    ],
}

INSTALL_SCRIPT_CMD = (
    "bash <(curl -fsSL https://raw.githubusercontent.com/Mrclocks/PGClockBot/main/get.sh)"
)

_REMOTE_NOTES_CACHE: dict[str, Any] = {"at": 0.0, "data": None, "ok": False}
_REMOTE_NOTES_TTL_OK = 300.0
_REMOTE_NOTES_TTL_FAIL = 30.0


def notes_for_version(version: str | None, source: dict[str, list[str]] | None = None) -> list[str]:
    if not version:
        return []
    key = str(version).strip().lstrip("vV")
    table = source if source is not None else RELEASE_NOTES_FA
    return list(table.get(key) or [])


def latest_notes_block(source: dict[str, list[str]] | None = None) -> dict[str, object] | None:
    table = source if source is not None else RELEASE_NOTES_FA
    for ver, notes in table.items():
        if notes:
            return {"version": ver, "notes": list(notes)}
    return None


def parse_release_notes_source(src: str) -> dict[str, list[str]]:
    """Extract RELEASE_NOTES_FA dict from release_notes.py source text."""
    tree = ast.parse(src)
    value_node = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "RELEASE_NOTES_FA":
                    value_node = node.value
                    break
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "RELEASE_NOTES_FA":
                value_node = node.value
        if value_node is not None:
            break
    if value_node is None:
        return {}
    try:
        raw = ast.literal_eval(value_node)
    except (ValueError, TypeError, SyntaxError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in raw.items():
        key = str(k).strip().lstrip("vV")
        if isinstance(v, (list, tuple)):
            notes = [str(x) for x in v if str(x).strip()]
            if notes:
                out[key] = notes
    return out


async def fetch_remote_release_notes(
    *,
    timeout: float = 4.0,
    force: bool = False,
) -> dict[str, list[str]] | None:
    """Download RELEASE_NOTES_FA from GitHub main (cached)."""
    now = time.monotonic()
    cached = _REMOTE_NOTES_CACHE.get("data")
    ttl = _REMOTE_NOTES_TTL_OK if _REMOTE_NOTES_CACHE.get("ok") else _REMOTE_NOTES_TTL_FAIL
    if (
        not force
        and isinstance(cached, dict)
        and (now - float(_REMOTE_NOTES_CACHE["at"])) < ttl
    ):
        return dict(cached)

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(
                GITHUB_RELEASE_NOTES_URL,
                headers={
                    "User-Agent": "PGClockBot-Panel",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
                params={"_": str(int(time.time()))} if force else None,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"status {resp.status_code}")
            parsed = parse_release_notes_source(resp.text or "")
            if not parsed:
                raise RuntimeError("empty release notes")
            _REMOTE_NOTES_CACHE.update({"at": now, "data": dict(parsed), "ok": True})
            return dict(parsed)
    except Exception as e:
        logger.debug("remote release notes fetch failed: %s", e)
        _REMOTE_NOTES_CACHE.update({"at": now, "data": cached if isinstance(cached, dict) else None, "ok": False})
        return dict(cached) if isinstance(cached, dict) else None


def changelog_for_update_page(
    *,
    local: str | None = None,
    remote: str | None = None,
    remote_notes: dict[str, list[str]] | None = None,
) -> dict:
    """Show changelog for the version the panel will update *to* when available."""
    local = (local or local_version() or "").strip()
    remote = (remote or "").strip() or None
    upgrading = bool(remote and is_newer(remote, local))

    if upgrading:
        ver = remote.lstrip("vV")
        # Prefer remote notes (what you are updating to); local may not have them yet.
        notes = notes_for_version(ver, remote_notes) or notes_for_version(ver)
        if notes:
            block = {"version": ver, "notes": notes}
        else:
            block = latest_notes_block(remote_notes) or {"version": ver, "notes": [
                "جزئیات این نسخه پس از دریافت از گیت‌هاب نمایش داده می‌شود."
            ]}
            # If fallback picked a different version, keep target version label when notes empty for it
            if block.get("version") != ver and not notes_for_version(ver, remote_notes):
                # Still OK to show newest remote block (usually same as target)
                pass
    else:
        ver = local.lstrip("vV")
        notes = notes_for_version(ver)
        block = {"version": ver, "notes": notes} if notes else latest_notes_block()

    blocks = [block] if block else []
    title = f"تغییرات نسخه {block['version']}" if block else "چنج‌لاگ"
    return {"title": title, "blocks": blocks, "has_notes": bool(blocks)}
