# PGClockBot v8.1.7 — Release Notes

**Tag:** `v8.1.7`  
**App version:** `8.1.7`  
**Restore point:** tag `v8.1.6`

---

## Bot settings back button

- The inline button under Settings subsections is now **⬅️ بازگشت** and actually goes back to the Settings hub.
- It no longer shows «دسترسی مالک سیستم لازم است» — that button is navigation, not an Owner check.
- Existing «adm:settings» callbacks on old messages also go back.

## Deploy

In-panel update to `8.1.7` (no new migration vs `v8.1.6`). Hard-refresh the panel after update. Restart the bot if it does not pick up the new version on its own.
