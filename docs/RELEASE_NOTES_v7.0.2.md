# PGClockBot v7.0.2 — Release Notes

**Tag:** `v7.0.2`  
**App version:** `7.0.2`

---

## Security

- Level-1 / Level-2 capability and role lookup uses that Principal’s (or reseller/staff) PasarGuard client. Owner `get_pg()` stays on Owner-only paths.
- At most one Owner principal (depth 0). Concurrent create is rejected by a unique index.
- `get_pg_for_principal()` selects by `principal_id` only; username is not a selector.
- Admin/Principal provision requires real PasarGuard `admins.create`, not `pg_admins` page visibility. Owner `pg_is_owner` still works.

## Deploy

In-panel update to `7.0.2`. Apply Alembic `0018_org_principal_single_owner` (unique Owner index). If an install already has two Owner rows, the migration fails until duplicates are resolved manually.
