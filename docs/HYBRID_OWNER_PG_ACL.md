# Hybrid Owner PasarGuard ACL

**Status:** Implemented  
**Branch:** `cursor/owner-pg-hybrid-clamp-0b9d`

## Policy

| Surface | Platform web Owner (`role=admin`) |
|---------|-----------------------------------|
| Shop (plans, orders, tickets, settings, backup, …) | Full allow (unchanged) |
| PasarGuard menus / pages / mutations | Clamped to env `PG_USERNAME` role |
| PG down / role unresolved | Fail-closed → no PG menus |

A true PasarGuard owner / sudo account still gets the full PG sidebar (including **ادمین**).

## Behavior

1. `require_staff` enriches Owner sessions via `enrich_platform_admin_staff` → live role from PasarGuard.
2. `can_pg_page` / `can_pg_action` / writes no longer auto-allow for `role=admin`.
3. Web sidebar and bot PG keyboards only list mapped features.
4. Setup probes PG login; limited accounts may finish with a warning (`pg_warn`).
5. `/pg/admins*` requires `pg_admins` (owner-only feature key).

## Security notes

- No token elevation: API calls still use the installer credentials.
- UI clamp + server `require_pg_perm` / `staff_pg_action` (not hide-only).
- Reseller / pg_staff paths unchanged (still no Owner-token fallback).
