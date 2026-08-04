# Phase C — Legacy Account Migration Notes

**Audience:** Operators deploying C5 (`0002_pg_staff_credentials`)  
**Schema change:** Additive nullable columns on `pg_staff_access` — `pg_admin_password_enc`, `pg_role_id`

---

## What happens on upgrade

1. Run Alembic: `alembic upgrade head` (or rely on SQLite legacy alter in `session.py`).  
2. Existing `PgStaffAccess` rows keep **NULL** encrypted password.  
3. Those users can still **log in** to the web panel (web password hash unchanged).  
4. PasarGuard list/mutate for those sessions **fail closed**:
   - Sidebar: overview only  
   - Lists: empty + isolation message  
   - Writes: error, never Owner token  

No data wipe. No credential auto-backfill (by design).

---

## Identify legacy accounts

```sql
SELECT id, pg_username, web_username, is_active,
       (pg_admin_password_enc IS NULL OR pg_admin_password_enc = '') AS missing_enc,
       pg_role_id
FROM pg_staff_access
WHERE is_active = true;
```

Rows with `missing_enc = true` need remediation before PG data access works.

---

## Remediation options (manual)

### Option A — Keep as bare pg_staff (PG menus only, no shop)

1. Staff logs into web panel with current web password.  
2. Opens **Security / credentials** (`/security`).  
3. Changes password (and optionally username).  
4. `change_staff_credentials` syncs PasarGuard password via Owner `modify_admin` and stores `pg_admin_password_enc`.  
5. Re-login (or refreshed session) → `pg_credentials_ready=true` → full mapped PG menus.

### Option B — Stay pg_staff via Owner (preferred once Phase D UI lands)

Phase D will expose Owner «اعطای / ویرایش دسترسی pg_staff» → `grant_web_access` / `update_web_access` (no reseller conversion).

Until then: use Option A (self-serve `/security`) or service-level `update_web_access`.

### Option C — Attach shop (become reseller) — explicit only

Only if the operator **wants** shop features:

1. Owner → `/pg/admins` → «ارتقای دسترسی وب» with plan + **new password**.  
2. Creates `ResellerProfile` and may remove `PgStaffAccess` (current UI).  
3. Account thereafter is a **reseller**, not pg_staff.

This is **not** required for PG panel access under the approved architecture.

### Option D — Revoke

Owner → revoke web access on `/pg/admins` if the account should not use the panel.

---

## New grants after C5

| Intent | What to do |
|--------|------------|
| Shop + PG secondary admin | Create PG admin with role → «اعطای دسترسی وب» with plan + password → becomes **reseller** |
| PG-only staff without shop | Service `grant_web_access` exists but is **not** exposed in Owner UI today — use Option A after a staff row exists, or treat as Phase D UI work |

---

## Reseller accounts

No migration required. Reseller `pg_admin_password_enc` model is unchanged. Continue using reseller edit / provision flows.

---

## Rollback

1. Revert C5 application commits if needed.  
2. `alembic downgrade 0001_baseline` drops the two columns.  
3. Without C5 code, bare pg_staff write path historically used Owner fallback — **do not roll back code without understanding that security regression**. Prefer forward remediation.
