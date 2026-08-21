# PGClockBot v8.1.16 — Release Notes

**Tag:** `v8.1.16`  
**App version:** `8.1.16`  
**Restore point:** tag `restore/pre-modal-tabs-scroll-perf-v8.1.15` (@ `v8.1.15`)

---

## مودال باشگاه — اسکرول تب‌ها

- اسکرول افقی تب‌ها با چرخ‌ماوس / ترک‌پد روی خود نوار تب کار می‌کند (دیگر فقط با کشیدن نوار اسکرول نیست).
- CSS تب‌های مودال مثل `pg-node-tabs`: `nowrap` + `overflow-x: auto` + `touch-action: pan-x`.

## سرعت لود اول

- واکشی `/home/body` و `/pg/body` زودتر (قبل از HTML سنگین شل) شروع می‌شود تا با پارس صفحه هم‌پوشانی داشته باشد.
- `/pg/body` دیگر تیکت/remediation کروم را دوباره نمی‌سازد (فقط لینک باز کردن پاسارگارد).
- Auth/ACL و `?full=1` بدون تغییر.

## Deploy

In-panel update to `8.1.16` (no new migration vs `v8.1.15`). Hard-refresh the panel after update.
