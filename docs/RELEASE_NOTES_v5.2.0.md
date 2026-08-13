# PGClockBot v5.2.0 — Release Notes

**Tag:** `v5.2.0`  
**App version:** `5.2.0`

**Restore point before this pack:** `restore-before-ux-pack-5b2d` (v5.1.9)

---

## Changes

- **Receipt photos** in the finance payments tab (Telegram `getFile` proxy + thumb).
- **User behavior:** step conversion rates and top abandoned plans (finance details).
- **Colors live preview** beside «رنگبندی دکمه‌ها» (tone-aware keyboard mock).
- **Staff order notes** editable from finance row actions.
- **PAYG risk strip** on admin home (suspended / low balance).
- **PAYG label** unified across bot + panel; remaining hardcoded confirm/reject styles wired to global colors.

## Deploy

1. Backup as usual.
2. Deploy `main` / tag `v5.2.0`.
3. Hard-refresh the panel (`panel.css` / preview JS).
