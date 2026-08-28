# PGClockBot v8.7.6 — Release Notes

**Tag:** `v8.7.6`  
**App version:** `8.7.6`  
**Restore point:** tag `restore/pre-v8.7.6-v8.7.5` (@ `v8.7.5`)

---

## وسط‌چین عمودی (ریشه‌ای)

### چک‌باکس جدول
- علت: `label { margin-bottom }` سراسری روی `.table-select-row` / `.table-select-all` دایره را به بالا هل می‌داد
- رفع: `margin: 0 !important` + `display: flex; align-items: center; justify-content: center; height: 100%; min-height: 48px` داخل سلول

### آکاردئون رنگبندی
- علت ۱: `.card:not(.card-flush)` → `display:flex` + `padding` + `gap` ارتفاع باکس را باد می‌کرد و محتوا بالا می‌ماند
- علت ۲: Safari/WebKit روی خود `<summary>` فلکس/گرید را درست اعمال نمی‌کند
- رفع: `padding/gap/flex` کارت صفر؛ wrapper داخلی `.colors-group-summary-inner` با grid و `height: 44px; align-items: center`
- فاصله بین گروه‌ها: `--space-1`

## Deploy

بدون مایگریشن. Hard refresh. SW: `pgclock-shell-v42`.
