# PGClockBot v8.2.9 — Release Notes

**Tag:** `v8.2.9`  
**App version:** `8.2.9`  
**Restore point:** tag `restore/pre-loyalty-tx-label-v8.2.8` (@ `v8.2.8`)

## What changed

1. **Loyalty transactions tab — user column**
   - Shows `name (@username)`, `@username`, or Telegram id instead of internal DB `user_id`

2. **Top referrers (overview)**
   - Same `bot_user_panel_label` format as tickets and other panel tables

3. **Shared helper**
   - `bot_user_panel_label()` in `formatting.py`; tickets page reuses it

## What this does *not* change

- Manual points adjust still uses internal user id (admin field)
- No migrations, no auth/ACL changes

## Update

In-panel update to `8.2.9` (no new migration). Hard-refresh the panel after update.
