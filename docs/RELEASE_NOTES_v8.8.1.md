# PGClockBot v8.8.1 — Release Notes

**Tag:** `v8.8.1`  
**App version:** `8.8.1`  
**Restore point:** tag `restore/pre-v8.8.1-v8.8.0` (@ `v8.8.0`)

---

## Panel UI polish

1. **Placeholders** — همه مثال‌های داخل input/textarea راست‌چین و کمرنگ در تم روشن و تیره (`--placeholder`)؛ فیلدهای `dir="ltr"` و `number` هم شامل
2. **سوییچ** — در حالت ON دایره داخل ترک می‌ماند (`--sw-travel: 16px` + clip)
3. **ui-select** — متن و caret وسط عمودی؛ لیبل خالی کمرنگ
4. **پیشنمایش تلگرام** — کپشن حذف؛ ارتفاع کمتر؛ دکمه‌های نمایش/بستن در موبایل تمام‌عرض
5. **چیدمان منو** — فاصله مخزن ↔ منوی فعال کمتر

## Deploy

بدون مایگریشن DB.

Hard refresh once. SW بدون تغییر اجباری.
