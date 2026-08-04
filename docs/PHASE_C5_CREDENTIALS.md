# Phase C5 — pg_staff Credential Sync

**Status:** Implemented  
**Branch:** `cursor/phase-c5-credential-sync-b96b`  
**Depends on:** C0–C4  
**Does not include:** Phase D identity unification

---

## Goal

Store encrypted PasarGuard passwords for `PgStaffAccess` (reseller pattern) and route all pg_staff reads/writes through `get_pg_for_staff` — **never** the Owner client.

## What changed

| Area | Change |
|------|--------|
| `PgStaffAccess` | `pg_admin_password_enc`, `pg_role_id` |
| Alembic `0002_pg_staff_credentials` | Add columns (idempotent) |
| SQLite legacy migrate | Same columns |
| `get_pg_for_staff` | Decrypt + authenticate as staff admin |
| `grant_web_access` / `update_web_access` / `change_staff_credentials` | Encrypt password; sync via owner `modify_admin` only |
| `staff_pg_read_client` / `_staff_pg` / `_assert_owned_user` | Use staff client when credentials exist |
| `require_staff` / login | Set `pg_credentials_ready`; prefer stored `pg_role_id`, refresh live |

## Behavior

| Principal | Without enc password | With enc password |
|-----------|----------------------|-------------------|
| pg_staff read | Fail closed (`PgReadDenied`) | `get_pg_for_staff` |
| pg_staff write | Fail closed | `get_pg_for_staff`, `as_owner=False` |
| pg_staff menu | Overview only | Mapped `pg_permissions` |
| Owner / Admin / Reseller | Unchanged | Unchanged |

Owner `get_pg().modify_admin` is used **only** to push the password into PasarGuard when granting/editing web access — never to act as the staff principal.

## Not changed

- Owner session / bot Owner tools  
- Reseller credential model  
- Shop authz (C4)  
- Database architecture beyond additive nullable columns  

## Rollback

1. Revert C5 commits.  
2. `alembic downgrade 0001_baseline` (drops columns).  
3. Legacy staff rows without enc remain fail-closed until re-granted with a password.

## Tests

`tests/test_phase_c5_credential_sync.py` plus updated C1/C2/full-audit expectations.
