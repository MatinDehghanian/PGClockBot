# PGClockBot v8.2.2 — Release Notes

**Tag:** `v8.2.2`  
**App version:** `8.2.2`  
**Restore point:** tag `restore/pre-panel-first-load-speed-v8.2.1` (@ `v8.2.1`)

## What changed

1. **Faster `/home` body (safe)**
   - Period sales (`shop_period_stats`): 12 sequential counts → 2 aggregated queries
   - Funnel / periods / action-center run in parallel on **isolated** DB sessions (no shared-session races)
   - Action-center “expiring” scan limited by max plan duration (no full-table service load)
   - PG role/capability cache TTL stays at **8s** (menus must not go stale)

2. **Loading UI**
   - Shell-first `/home` shows a clock placeholder (like `/pg`) instead of unchecked zeros
   - Slow in-panel navigation: matte full-viewport clock veil after ~150ms; page content stays under the veil (no blank flash / no hide-on-arrive)

## What this does *not* change

- No SPA navigation, no auth/ACL shortcuts, no brand cold-boot splash
- No new migrations

## Update

In-panel update to `8.2.2` (no new migration). Hard-refresh the panel after update.
