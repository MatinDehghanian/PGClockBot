# PGClockBot v8.1.15 — Release Notes

**Tag:** `v8.1.15`  
**App version:** `8.1.15`  
**Restore point:** branch `cursor/restore-before-shop-settings-scope-ffcf` / tag `restore/pre-shop-settings-scope-v8.1.14` (@ `v8.1.14`)

---

## Shop/Settings scope (surgical)

- Finance / Supports: scoped staff without resolvable `shop_owner_id` no longer falls through to Owner `settings` (empty/degraded instead).
- Owner live settings load only for real Owner (`is_platform_admin`).
- Shop Settings GET/POST: session `shop_owner_id` (reseller or principal with valid profile), not `role=="reseller"` alone.
- Client-supplied `reseller_id` is ignored; read and write use the same server scope.

## Deploy

In-panel update to `8.1.15` (no new migration vs `v8.1.14`). Hard-refresh the panel after update.
