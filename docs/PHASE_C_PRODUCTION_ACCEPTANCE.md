# Phase C — Production-Safety Acceptance Report (C0–C5)

**Date:** 2026-08-04  
**Mode:** Verification only — **no code changes**  
**Code tip verified:** `cursor/phase-c5-credential-sync-b96b` @ `01c86e3`  
**Docs branch:** `cursor/phase-c-acceptance-phase-d-plan-b96b`

---

## Automated verification

| Suite | Result |
|-------|--------|
| `tests/test_phase_c0_authz.py` | PASS |
| `tests/test_phase_c1_read_isolation.py` | PASS |
| `tests/test_phase_c2_write_authz.py` | PASS |
| `tests/test_phase_c3_limits_quotas.py` | PASS |
| `tests/test_phase_c4_bot_web_alignment.py` | PASS |
| `tests/test_phase_c5_credential_sync.py` | PASS |
| `tests/test_full_audit_3_8_3.py` | PASS |
| `tests/test_owner_bypass_guards.py` | PASS |
| `tests/test_tenant_isolation.py` | PASS |
| `tests/test_pg_admin_web_gate.py` | PASS |
| `tests/test_pg_web_access_guards.py` | PASS |
| `UpdateWebAccessOptionalPasswordTests` | PASS |

**Total this pass: 142 passed, 0 failed**

---

## Workflow matrix

### 1. Owner — create / role / credentials / access

| Step | Result | Notes |
|------|--------|-------|
| Create PG admin | **PASS** | `POST /pg/admins` → `create_admin` with optional `role_id` |
| Assign PG role | **PASS** | Role chosen at create time in PasarGuard; web grant only caches `pg_role_id` |
| Sync credentials (product path) | **PASS*** | Current Owner UI «اعطای / ارتقای دسترسی وب» → `provision_existing_pg_admin` → **Reseller** with enc when password set |
| Sync credentials (bare `PgStaffAccess`) | **PARTIAL** | `grant_web_access` / `update_web_access` encrypt + `modify_admin`, but **no HTTP route** wires them; toggle/revoke still hit `PgStaffAccess` |
| Confirm no Owner-token staff ops | **PASS** | `_staff_pg` / reads never `get_pg(), True` for non-admin |

\*Product intent today: secondary web users with shop are **resellers**, not bare `pg_staff`. Modal copy: «ارتقای دسترسی وب» / plan required.

### 2. pg_staff — login / menus / reads / forbid / no Owner fallback

| Check | Result |
|-------|--------|
| Login with web hash | **PASS** (enc not required to authenticate) |
| Sidebar menus without enc | **PASS** — `effective_pg_menu_keys` → overview only |
| Sidebar menus with enc | **PASS** — full mapped `pg_permissions` |
| Read allowed resources (with enc) | **PASS** — `get_pg_for_staff` |
| Read/write without enc | **PASS** — fail closed (`PgReadDenied` / `PasarGuardError`) |
| Cannot fallback to Owner | **PASS** — owner client not used for staff ops |
| Deep-link to forbidden page | **PARTIAL** — route ACL still allows mapped keys; **data** fail-closed (empty + isolation message), not hard 403 |

### 3. Legacy pg_staff (null `pg_admin_password_enc`)

| Check | Result |
|-------|--------|
| Migration leaves enc NULL | **PASS** — Alembic `0002` nullable, no backfill |
| No Owner fallback | **PASS** |
| No crash | **PASS** — caught → empty lists / redirects |
| Clear status | **PARTIAL** — PG overview / list flash shows isolation Persian message; **no** dedicated login banner or Owner admin badge for “credentials missing” |
| Until sync | Login OK; PG data ops denied; sidebar overview-only |

### 4. Reseller

| Check | Result |
|-------|--------|
| Own credentials only | **PASS** — `get_pg_for_reseller` |
| No Owner fallback | **PASS** |
| Shop scope unchanged | **PASS** |

### 5. Bot / Web shop permissions

| Check | Result |
|-------|--------|
| Same ACL source (`web_permissions`) | **PASS** |
| Empty ACL denies both | **PASS** (C4) |
| Admin bypass both | **PASS** |
| Bot PG tools still platform-admin only | **PASS** (explicit non-goal for C4) |

---

## Security invariants (binding)

1. **No Owner client** for reseller or pg_staff list/mutate.  
2. Missing encrypted password → **fail closed**.  
3. Owner `modify_admin` only for **password sync**, never to act as staff.  
4. Bot shop feature outcomes match Web shop feature outcomes.  
5. Additive schema only (`pg_admin_password_enc`, `pg_role_id`).

All five hold under static review + automated tests.

---

## Known operational gaps (accepted for Phase C; candidates for Phase D)

1. Owner HTTP path does not call `grant_web_access` — new web grants become **resellers**.  
2. Re-credentialing **bare** legacy `pg_staff` without converting to reseller: service exists; UI path is **self-serve `/security` password change** (`change_staff_credentials`) or convert via «ارتقای دسترسی وب» with a new password.  
3. Upgrading legacy staff with **blank** password can produce a reseller **without** `pg_admin_password_enc` (same fail-closed). Operators must set a password when upgrading.  
4. Menu clamp vs deep-link: overview-only nav; deep links show empty data rather than 403.  
5. No Owner column/badge for `pg_credentials_ready` on staff rows.

These do **not** reintroduce Owner fallback.

---

## Overall verdict

**GREEN for Phase C security acceptance** — production-safe to operate under the documented migration steps below.

**CONDITIONAL on ops:** Owners must remediate legacy `PgStaffAccess` rows (or upgrade them to reseller with password) before those accounts can use PG data pages.

Proceed to **Phase D planning only** (no implementation in this pass).

---

## Related PRs

| Phase | PR |
|-------|----|
| Analysis | #134 |
| C0 | #135 |
| C1 | #136 |
| C2 | #137 |
| C3 | #138 |
| C4 | #139 |
| C5 | #140 |
