# PGClockBot v8.5.1 — Release Notes

**Tag:** `v8.5.1`  
**App version:** `8.5.1`  
**Restore point:** tag `restore/pre-ui-preview-users-fix-v8.5.0` (@ `v8.5.0`)

## Fixes

1. **Telegram settings preview**
   - Opens inside the same preview card; «نمایش پیش‌نمایش» hides while open and returns on close
   - Close button is full-width (mobile-friendly)

2. **Users table**
   - Alert = orange dot only; risk = yellow badge (same size as role tags)
   - Narrower service column; compact service picker with per-service boxes + alert dots
   - Vertically aligned with row content (no tall ui-select)
   - Edit modal open path fixed (`data-user-edit-open` + explicit `openModal`)

3. **Finance reports**
   - Removed redundant day/week/month section-tabs (compare cards remain the selector)

## Deploy

In-panel update to `8.5.1` (no new migration). Hard-refresh after update.
