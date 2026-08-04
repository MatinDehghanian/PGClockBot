# PGClockBot v4.0.0 — Release Notes

**Tag:** `v4.0.0`  
**Commit:** `c792b6acde6711c10f3cc098669471e37411113f` (merge of tested tip `68163de` + release docs)  
**Includes:** Phase A/B + C0–C5 + D1–D4  
**Ops runbook:** `docs/V4_RELEASE_CHECKLIST.md`  
**Audit:** `docs/FINAL_RELEASE_AUDIT.md`

---

## Highlights

v4 ships the Phase C/D authorization and identity stack on top of Phase A (PostgreSQL/Alembic) and Phase B (`pgclock` CLI):

- Unified authz decision layer (Web + Bot shop ACL)
- Fail-closed PasarGuard clients for reseller / pg_staff (no Owner fallback)
- First-class `pg_staff` (PG-only) alongside Reseller
- PasarGuard-aligned credential policy and dual grant flows
- Legacy staff remediation (confirm-align, inventory, CTAs)
- Documented Web/Bot identity matrix

---

## Database changes

| Revision | Change |
|----------|--------|
| `0001_baseline` | Alembic baseline matching app models (Phase A) |
| `0002_pg_staff_credentials` | Additive nullable columns on `pg_staff_access`: `pg_admin_password_enc`, `pg_role_id` (Phase C5) |

- No credential auto-backfill (by design).
- Existing staff rows keep NULL enc until remediated; web login via bcrypt still works.
- SQLite and PostgreSQL both supported; Postgres preferred.

**Migrate:** `alembic upgrade head` (or `pgclock migrate`) → confirm `0002_pg_staff_credentials`.

---

## Security improvements

- No Owner-token fallback for reseller or pg_staff PG reads/writes.
- Staff without stored enc: overview-only menus; lists/writes fail closed.
- Password strength unified to PasarGuard rules (D1) across create/update/sync/CLI.
- Encrypt failure fails closed (no “success” without usable enc).
- Owner `modify_admin` used only for intentional password sync on grant/edit.

---

## Permission changes

- Shop features: single source `web_permissions` for Web and Bot (C4); `bot_permissions` remains a write mirror only.
- PG page/actions: role-mapped matrices via `authz` / `pg_access`.
- Quotas/HWID: RoleLimits parity for staff/reseller (C3).
- Bot PG management remains **platform-admin only**; reseller/staff manage PG on **Web**.

---

## Identity changes

| Principal | Web | Shop | PG client | Bot |
|-----------|-----|------|-----------|-----|
| Owner / platform Admin | `web_admin.json` → `role=admin` | Full | `get_pg()` | `ADMIN_IDS` / `BotUser.admin` (independent) |
| pg_staff | `PgStaffAccess` | None | `get_pg_for_staff` | Web-only |
| Reseller | `ResellerProfile` | C4 ACL | `get_pg_for_reseller` | Shop bot |

- Dual Owner grants: **اعطای ادمین فرعی** vs **اعطای نماینده** (no silent conversion).
- Staff `web_username` must equal `pg_username`; mismatch requires confirm-align (D3).
- Identity help on `/security` (D4).

---

## Migration notes (operators)

1. Backup: `pgclock backup --note "pre-v4-release"`.
2. Stop service → `alembic upgrade head` → start → `pgclock health`.
3. Inventory legacy staff: `python -m scripts.list_pg_staff_remediation --needs-remediation`.
4. Remediate L1/L2/L4 via Owner staff edit (confirm-align + D1 password).
5. Configure **both** Web Owner and Bot `ADMIN_IDS` if the same person needs both channels.
6. Do **not** use reseller grant to “fix” staff.

Full checklist: `docs/V4_RELEASE_CHECKLIST.md`.

---

## Rollback notes

- Prefer **forward remediation** and application restore from `pgclock restore <id>`.
- Avoid `alembic downgrade` past C5 in production (drops enc columns; older code may Owner-fallback).
- Do not roll back the D2 dual-grant split (silent staff→reseller conversion returns).

---

## Verification at tag time

- `git status` clean on `main`
- Ancestor includes `68163de` (D4 tip)
- Phase B–D4 + isolation/security/smoke: **267 passed**
