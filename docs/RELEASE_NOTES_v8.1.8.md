# PGClockBot v8.1.8 — Release Notes

**Tag:** `v8.1.8`  
**App version:** `8.1.8`  
**Restore point:** tag `v8.1.7`

---

## Bot settings inline buttons

- All inline buttons inside Settings (`adm:st:*`, including **➕ پشتیبان جدید**) now work after owner-gated reply navigation.
- The Owner Principal gate no longer re-runs on every in-flow settings click or FSM message.
- Forged settings callbacks outside the settings nav stack are still denied.

## Deploy

In-panel update to `8.1.8` (no new migration vs `v8.1.7`). Hard-refresh the panel after update. Restart the bot if needed.
