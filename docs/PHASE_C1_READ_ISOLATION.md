# Phase C1 — Read Isolation

**Status:** Implemented  
**Branch:** `cursor/phase-c1-read-isolation-b96b`  
**Depends on:** Phase C0 (`authz` foundation)

---

## Scope

Tenant-safe **reads only** for: users, templates, groups, hosts, nodes, inbounds.

## What changed

| File | Change |
|------|--------|
| `app/services/pg_read.py` | **New** — `staff_pg_read_client`, menu key alignment, fail-closed helpers |
| `app/api/pg_pages.py` | GET list pages use read client; `_pg_ctx` aligns sidebar with safe reads |
| `app/services/plans_catalog.py` | `load_pg_plan_options` tenant-safe; allow-list `None` fail-closed unless trusted client |
| `app/services/pg_overview.py` | Overview uses read client; removed unscoped user-list fallback |
| `app/api/app.py` / `home_pages.py` / bot reseller plans | Pass `session` into plan options / overview |
| `tests/test_phase_c1_read_isolation.py` | C1 isolation tests |

## Behavior

| Principal | List/GET client |
|-----------|-----------------|
| Owner / platform admin | `get_pg()` (unchanged) |
| Reseller | `get_pg_for_reseller` — **no owner token** |
| pg_staff | **No read client** until C5 — empty lists + isolation message; menu shows overview only |

## Not changed (deferred)

- Write / `_staff_pg` mutation path (C2)
- Quotas / HWID (C3)
- Bot keyboard parity (C4)
- pg_staff PG credentials (C5)
- `_assert_owned_user` owner+filter for pg_staff write prelude (left for C2/C5)

## Known limitation

pg_staff cannot list PG resources until C5 stores their credentials. Writes still use prior `_staff_pg` owner path (unchanged in C1).

## Test results

```text
tests/test_phase_c0_authz.py
tests/test_phase_c1_read_isolation.py
tests/test_wholesale_menu_qr_stats_3_3_8.py
tests/test_security_audit_hardening.py
tests/test_owner_bypass_guards.py
tests/test_tenant_isolation.py
tests/test_production_audit_3_5_6.py

104 passed, 0 failed
```

## Rollback

Revert C1 commits on `cursor/phase-c1-read-isolation-b96b`. No DB migrations.