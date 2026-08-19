# PGClockBot v8.1.6 — Release Notes

**Tag:** `v8.1.6`  
**App version:** `8.1.6`  
**Restore point:** tag `v8.1.5`

---

## Bot inline settings back button

- The inline **⬅️ تنظیمات** button no longer false-denies the real Owner with «دسترسی مالک سیستم لازم است».
- Aiogram 3.x unwraps handler decorators before dependency injection; the Owner gate now keeps `session` visible to the dispatcher.

## Deploy

In-panel update to `8.1.6` (no new migration vs `v8.1.5`). Hard-refresh the panel after update.
