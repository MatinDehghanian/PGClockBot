# PGClockBot v8.5.16 — Release Notes

**Tag:** `v8.5.16`
**App version:** `8.5.16`
**Restore point:** tag `v8.5.15`

## Fixes

1. **Mobile black bar / Safari glass (new root cause)**
   - `100dvh` on first paint mismatched Safari chrome → dead strip until scroll → switch to **`100svh`**
   - Closed hamburger drawer stayed `position:fixed` full-height off-screen → Safari 26 sampled its dark bg → **collapse closed drawer to `height:0`**
   - Opaque `--background` on `.main` under the tab bar forced solid black chrome → **transparent** on `ios-safari` for html/body/shell/main
   - Service worker cache bumped to **`v6`**

2. **Users table restored**
   - Accidental v8.2.12 CSS/JS revert had broken tags + service menu
   - Restored approved v8.5.8 polish (tags wrap, boxed service menu, alert dots, centered select)

3. **Inbox / daily actions**
   - Action items vertically centered in their boxes (`align-items: center`)

## Deploy

1. Update to **8.5.16**
2. Clear Safari website data for the panel host once (SW v6)
3. Reopen and check bottom bar + users table + inbox
