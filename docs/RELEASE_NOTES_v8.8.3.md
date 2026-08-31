# PGClockBot v8.8.3 — Release Notes

**Tag:** `v8.8.3`  
**App version:** `8.8.3`  
**Restore point:** tag `restore/pre-v8.8.3-v8.8.2` (@ `v8.8.2`)

---

## Panel UI

1. **تم روشن موبایل** — ریشهٔ نوار سفید دراور بسته: قانون سراسری `html[data-theme=light] .side { #fff }` دیگر cascade موبایل را override نمی‌کند (پوسته transparent؛ رنگ روی `.side-panel`)
2. **منوی بات** — فاصله همه باکس‌ها مثل پیش‌نمایش↔چیدمان (`--stack-gap`)؛ بدون جمع‌شدن margin کارت با gap
3. **حالت چیدمان کیبورد** — متن ui-select وسط عمودی (قانون عنوان دیگر `.ui-select-label` را نمی‌گیرد)

## Deploy

بدون مایگریشن DB.

Hard refresh once.
