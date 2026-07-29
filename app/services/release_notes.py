"""Persian release notes shown on the panel update page."""

from __future__ import annotations

from app.services.updates import is_newer, local_version

# Newest first. Keep short and scannable — UI shows only the latest version block.
RELEASE_NOTES_FA: dict[str, list[str]] = {
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


def notes_for_version(version: str | None) -> list[str]:
    if not version:
        return []
    key = str(version).strip().lstrip("vV")
    return list(RELEASE_NOTES_FA.get(key) or [])


def latest_notes_block() -> dict[str, object] | None:
    for ver, notes in RELEASE_NOTES_FA.items():
        if notes:
            return {"version": ver, "notes": list(notes)}
    return None


def changelog_for_update_page(*, local: str | None = None, remote: str | None = None) -> dict:
    """Single-version changelog: only the newest relevant release notes."""
    local = (local or local_version() or "").strip()
    remote = (remote or "").strip() or None

    if remote and is_newer(remote, local):
        ver = remote.lstrip("vV")
    else:
        ver = local.lstrip("vV")

    notes = notes_for_version(ver)
    if notes:
        block = {"version": ver, "notes": notes}
    else:
        block = latest_notes_block()

    blocks = [block] if block else []
    title = f"تغییرات نسخه {block['version']}" if block else "چنج‌لاگ"
    return {"title": title, "blocks": blocks, "has_notes": bool(blocks)}
