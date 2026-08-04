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

### Option B — Upgrade to reseller (shop + PG) — current Owner UI

1. Owner → `/pg/admins` → row source `pg_staff` → **ویرایش دسترسی / ارتقای دسترسی وب**.  
2. Select a **reseller plan** (required).  
3. Set a **new password** (do not leave blank if enc was null — blank keeps old web hash but may leave PG enc empty).  
4. Submit → `provision_existing_pg_admin` creates `ResellerProfile`, syncs enc when password provided, **deletes** the `PgStaffAccess` row.  
5. Account thereafter logs in as **reseller** (shop ACL from plan + PG from role).

### Option C — Revoke

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
