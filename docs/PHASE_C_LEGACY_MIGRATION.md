# Phase C / D — Legacy Account Migration Notes

**Audience:** Operators after C5 (`0002_pg_staff_credentials`) and Phase D grant/remediation  
**Schema change (C5):** Additive nullable columns on `pg_staff_access` — `pg_admin_password_enc`, `pg_role_id`

---

## What happens on upgrade (C5)

1. Run Alembic: `alembic upgrade head` (or rely on SQLite legacy alter in `session.py`).  
2. Existing `PgStaffAccess` rows keep **NULL** encrypted password.  
3. Those users can still **log in** to the web panel (web password hash unchanged).  
4. PasarGuard list/mutate for those sessions **fail closed**:
   - Sidebar: overview only  
   - Lists: empty + isolation message  
   - Writes: error, never Owner token  

No data wipe. No credential auto-backfill (by design).

---

## Identify accounts needing remediation (D3)

```bash
.venv/bin/python -m scripts.list_pg_staff_remediation --needs-remediation
```

Or SQL:

```sql
SELECT id, pg_username, web_username, is_active,
       (pg_admin_password_enc IS NULL OR trim(pg_admin_password_enc) = '') AS missing_enc,
       (lower(web_username) = lower(pg_username)) AS username_aligned,
       pg_role_id
FROM pg_staff_access
ORDER BY is_active DESC, missing_enc DESC, username_aligned ASC;
```

Owner UI (`/pg/admins`) shows badges for missing enc and username mismatch.

---

## Remediation (keep as pg_staff)

### Preferred — Owner staff edit (D2/D3)

1. Owner → `/pg/admins` → **ویرایش دسترسی ادمین فرعی**.  
2. If username mismatched: check **هم‌ترازسازی نام کاربری با پاسارگارد** (D3 Q1 A — not silent).  
3. Set a D1-strong password (required when enc missing).  
4. Row stays `PgStaffAccess`; enc + bcrypt + `modify_admin` sync.  
5. Staff re-login → `pg_credentials_ready=true` → mapped PG menus.

### Self-serve — only when username already aligned

1. Staff → `/security` → change password.  
2. Same sync path; stays pg_staff.  
3. If `web ≠ pg`, self-serve errors (no auto-rename) — Owner must confirm-align first.

### Do **not** use reseller grant to “fix” staff

«اعطای نماینده» refuses when a staff row exists (D2). To become a reseller intentionally: **revoke** staff first, then grant reseller. No automatic conversion.

### Revoke

Owner → revoke web access on `/pg/admins` if the account should not use the panel.

---

## Dual grants after D2

| Intent | What to do |
|--------|------------|
| PG-only staff (pg_staff) | `/pg/admins` → **اعطای ادمین فرعی** → `…/web-access/staff` |
| Shop + PG reseller | `/pg/admins` → **اعطای نماینده** (only if no staff row) → `…/web-access/reseller` |

Old `POST …/web-access` hard-fails (obsolete).

---

## Reseller accounts

No staff→reseller migration required. Null-enc resellers: remediate via reseller password UI. Pre-D2 converted resellers: leave as reseller.

---

## Rollback

1. Prefer forward remediation (D3 badges + confirm-align + inventory).  
2. `alembic downgrade` past C5 drops enc columns — **critical**; old code may Owner-fallback.  
3. Do not roll back D2 grant split in production (silent conversion returns).
