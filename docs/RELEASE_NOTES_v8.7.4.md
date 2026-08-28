# PGClockBot v8.7.4 — Release Notes

**Tag:** `v8.7.4`  
**App version:** `8.7.4`  
**Restore point:** tag `restore/pre-v8.7.4-v8.7.3` (@ `v8.7.3`)

---

## اصلاحات UX پنل (بعد از v8.7.3)

### اعلان‌ها — رفع بازنشانی و کلید dismiss

- کلید پایدار `op:{org_principal_id}` برای همه نقش‌ها
- بارگذاری/پاک‌سازی روی کلید canonical + همه legacyها
- upsert: ادغام ردیف‌های تکراری legacy
- sidebar dot فقط وقتی اعلان واقعاً visible است (نه unread خام)

### تب رنگبندی — آکاردئون RTL

- متن راست، دایره chevron چپ (`direction: rtl` + flex)
- رفع override اشتباه `display: block` روی summary

### جداول — چک‌باکس bulk

- 16×16px مربع با گوشه 4px (هم‌اندازه tag)
- ستون انتخاب سمت چپ (قبل از actions)
- `-webkit-appearance: none` برای iOS

## Deploy

بدون مایگریشن DB.

Hard refresh once after update. SW: `pgclock-shell-v40`. Restore: `restore/pre-v8.7.4-v8.7.3`.
