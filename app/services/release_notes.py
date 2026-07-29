"""Persian release notes shown on the panel update page."""

from __future__ import annotations

from app.services.updates import is_newer, local_version

# Newest first within each version. Keep short and scannable.
RELEASE_NOTES_FA: dict[str, list[str]] = {
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


def notes_for_version(version: str | None) -> list[str]:
    if not version:
        return []
    key = str(version).strip().lstrip("vV")
    return list(RELEASE_NOTES_FA.get(key) or [])


def changelog_between(local: str | None, remote: str | None) -> list[dict[str, object]]:
    """Notes for versions newer than local up to remote (remote first)."""
    local = (local or local_version() or "").strip().lstrip("vV")
    remote = (remote or "").strip().lstrip("vV")
    if not remote:
        return []
    items: list[dict[str, object]] = []
    for ver, notes in RELEASE_NOTES_FA.items():
        if not notes:
            continue
        if local and not is_newer(ver, local):
            continue
        if remote and is_newer(ver, remote):
            continue
        items.append({"version": ver, "notes": list(notes)})
    # Already newest-first because dict insertion order matches RELEASE_NOTES_FA
    return items


def recent_changelog(*, limit: int = 4) -> list[dict[str, object]]:
    """Newest release notes with content, for idle update page."""
    items: list[dict[str, object]] = []
    for ver, notes in RELEASE_NOTES_FA.items():
        if not notes:
            continue
        items.append({"version": ver, "notes": list(notes)})
        if len(items) >= max(1, limit):
            break
    return items


def changelog_for_update_page(*, local: str | None = None, remote: str | None = None) -> dict:
    local = (local or local_version() or "").strip()
    remote = (remote or "").strip() or None
    if remote and is_newer(remote, local):
        blocks = changelog_between(local, remote)
        if not blocks:
            # Remote newer but no curated notes yet — still show recent history
            blocks = recent_changelog(limit=4)
        title = f"تغییرات تا نسخه {remote}"
    else:
        notes = notes_for_version(local)
        if notes:
            blocks = [{"version": local.lstrip("vV"), "notes": notes}]
            title = f"تغییرات نسخه {local.lstrip('vV')}"
        else:
            blocks = recent_changelog(limit=4)
            title = "آخرین تغییرات"
    return {"title": title, "blocks": blocks, "has_notes": bool(blocks)}
