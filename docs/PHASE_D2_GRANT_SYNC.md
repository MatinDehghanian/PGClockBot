# Phase D2 — Grant Flow + Username Sync (Implemented)

**Status:** Implemented — stop before D3  
**Branch:** `cursor/phase-d2-grant-sync-b96b`  
**Depends on:** D1 approved · D2 plan approved (Q1–Q3)

---

## Decisions applied

| Q | Choice |
|---|--------|
| Q1 | **Error-only** — no auto-rename when `web ≠ pg` |
| Q2 | Old `POST …/web-access` **hard-fails** (no alias) |
| Q3 | Reseller revoke out of scope |

---

## What changed

| Area | Behavior |
|------|----------|
| `POST …/web-access/staff` | `grant_web_access` / `update_web_access` |
| `POST …/web-access/reseller` | `provision_existing_pg_admin` |
| `POST …/web-access` | Hard fail redirect message |
| `provision_existing_pg_admin` | Refuses if `PgStaffAccess` exists; **no** `revoke_web_access` |
| pg_staff username | `assert_web_matches_pg` on grant/update/change |
| UI | Dual buttons/modals; username locked to PG name |

## Not changed

- Permissions / authz  
- Bot logic  
- Owner ↔ `PG_PASSWORD` sync  
- Automatic staff→reseller migrate (still deferred)  
- Owner fallback (still forbidden)

## Tests

`tests/test_phase_d2_grant_sync.py` + Phase C/D1 regression.
