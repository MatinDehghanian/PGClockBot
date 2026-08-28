# PGClockBot v8.7.3 — Release Notes

**Tag:** `v8.7.3`  
**App version:** `8.7.3`  
**Restore point:** tag `restore/pre-v8.7.3-v8.7.2` (@ `v8.7.2`)

---

## اصلاحات UX پنل (بعد از v8.7.2)

### اعلان‌ها — رفع نمایش و dismiss پایدار

- کلید dismiss پایدار با `org_principal_id` / `pg_staff_id` / `bot_user_id`
- بارگذاری و پاک‌سازی dismiss روی کلید فعلی + legacy
- کارت **«بازنشانی اعلان‌های مخفی»** همیشه بالای `/inbox` (بدون شرط تعداد dismiss)
- شمارنده «اعلان مخفی شده» در همان کارت

### تب رنگبندی

- حذف کامل پیش‌نمایش تلگرام (admin + shop settings)
- آکاردئون: تراز عمودی، chevron بالا/پایین، فاصله `--section-gap`

### سایر

- چک‌باکس multi-select: 20×20px (هم‌ارتفاع badge/tag)
- پاک‌سازی کد مرده preview رنگ‌ها

## Deploy

بدون مایگریشن DB.

Hard refresh once after update. SW: `pgclock-shell-v39`. Restore: `restore/pre-v8.7.3-v8.7.2`.
