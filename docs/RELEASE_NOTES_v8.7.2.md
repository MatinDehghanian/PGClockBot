# PGClockBot v8.7.2 — Release Notes

**Tag:** `v8.7.2`  
**App version:** `8.7.2`  
**Restore point:** tag `restore/pre-v8.7.2-v8.7.1` (@ `v8.7.1`)

---

## اصلاحات UX پنل (بعد از v8.7.1)

### اعلان‌ها — رفع ناپدید شدن بعد از آپدیت

- **cleanup** دیگر فقط `entries` را نمی‌بیند — شمارنده‌های واقعی (`pending`، `tickets`، …) هم لحاظ می‌شوند
- اگر build صف کار fail شود، cleanup اجرا نمی‌شود
- دکمه **«بازنشانی اعلان‌های مخفی»** در `/inbox` (`POST /inbox/dismiss/reset`)

### تب رنگبندی — بازطراحی

- حذف کامل چیپ‌های دایره‌ای — فقط **select رنگ**
- آکاردئون فشرده‌تر، فلش به بالا وقتی باز است
- فاصله‌های کمتر بین گروه‌ها

### سایر

- حذف مقصد پرداخت: `btn-danger` مثل بقیه دکمه‌های حذف
- چک‌باکس multi-select کوچک‌تر (15px)
- همه سوییچ‌ها یک اندازه (44×26)

## Deploy

بدون مایگریشن DB.

Hard refresh once after update. SW: `pgclock-shell-v38`. Restore: `restore/pre-v8.7.2-v8.7.1`.
