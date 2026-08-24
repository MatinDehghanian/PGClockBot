# PGClockBot v8.2.10 — Release Notes

**Tag:** `v8.2.10`  
**App version:** `8.2.10`  
**Restore point:** tag `restore/pre-settings-preview-lazy-v8.2.9` (@ `v8.2.9`)

## What changed

1. **Telegram settings preview is lazy**
   - Closed by default on menu / buttons / colors / QR / appearance / messages / daily report
   - Gate card: «نمایش پیش‌نمایش» — phone mock + live listeners only after click
   - «بستن پیش‌نمایش» removes sticky column and unbinds listeners

2. **Lighter scroll/typing**
   - No sticky preview column until open
   - Debounced live render (~180ms) while open

## What this does *not* change

- No migrations, no auth/ACL changes
- Preview visuals unchanged once opened; gate matches settings-card language

## Update

In-panel update to `8.2.10` (no new migration). Hard-refresh the panel after update.
