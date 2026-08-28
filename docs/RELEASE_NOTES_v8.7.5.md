# PGClockBot v8.7.5 — Release Notes

**Tag:** `v8.7.5`  
**App version:** `8.7.5`  
**Restore point:** tag `restore/pre-v8.7.5-v8.7.4` (@ `v8.7.4`)

---

## اصلاحات

### اعلان‌ها
- reset و load با clause مشترک روی همه کلیدهای legacy (`op:`, `admin:username`, `admin:pN`, …)
- upsert: ادغام duplicateها بدون خطای `MultipleResultsFound`
- sidebar dot فقط از نتیجه فیلترشده `/inbox`

### چک‌باکس جداول
- **برگشت:** ستون انتخاب سمت راست (اولین ستون RTL)
- **دایره** (نه مربع)، قطر **۲۰px** = `min-height` تگ `.badge`
- `appearance: none !important` تا Safari اندازه native را باد نکند

### آکاردئون رنگبندی
- layout با CSS grid RTL: عنوان راست، دایره chevron چپ، `align-items: center`
- حذف `margin-bottom` دوبل `settings-card` داخل stack
- فاصله بین گروه‌ها: `--space-2`

## Deploy

بدون مایگریشن DB.

Hard refresh once. SW: `pgclock-shell-v41`. بعد از آپدیت یک‌بار «بازنشانی اعلان‌های مخفی» بزنید.
