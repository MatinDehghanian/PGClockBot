# PGClockBot v8.1.12 — Release Notes

**Tag:** `v8.1.12`  
**App version:** `8.1.12`  
**Restore point:** tag `restore/pre-message-variables-v8.1.11` (@ `v8.1.11`)

---

## متغیرهای پیام (کاتالوگ)

- صفحهٔ خواندنی `/message-variables` در سایدبار بخش ربات، **قبل از تنظیمات**.
- فهرست گروه‌بندی‌شدهٔ جای‌نگهدارهای `{snake_case}` با توضیح فارسی، مثال، نام‌های قدیمی، و دکمهٔ کپی.
- دسترسی: همان `shop_settings`؛ مالکان سیستم متغیرهای نام‌گذاری پاسارگارد را می‌بینند؛ نماینده/غیرمالک نه.
- بدون نمایش توکن، رمز، یا شناسه‌های سیستم.

## رندر امن متن‌ها

- مسیر مرکزی `render_message_template` با دامنهٔ محدود + `safe_format` (بدون `str.format`).
- اتصال به خوش‌آمد، پرداخت، کیف پول، دعوت، تحویل سفارش، کپشن QR، عضویت اجباری، و الگوی نام کاربری.
- رفع باگ: پیام عضویت اجباری دیگر با `.format(channels=…)` رندر نمی‌شود (امن در برابر تزریق format).

## Deploy

In-panel update to `8.1.12` (no new migration vs `v8.1.11`). Hard-refresh the panel after update.
