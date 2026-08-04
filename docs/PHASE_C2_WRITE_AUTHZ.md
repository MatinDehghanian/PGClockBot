# Phase C2 — Write Authorization

**Status:** Implemented  
**Branch:** `cursor/phase-c2-write-authz-b96b`  
**Depends on:** C0 + C1

---

## Scope

Mutation client selection + ownership probes for writes. Exact action gates already present on POSTs are retained.

## Changes

| File | Change |
|------|--------|
| `app/api/pg_pages.py` | `_staff_pg`: no owner fallback for pg_staff; `_assert_owned_user`: no owner probe for pg_staff |
| `tests/test_phase_c2_write_authz.py` | New |
| `tests/test_full_audit_3_8_3.py` | Expect C2 fail-closed (was as_owner path) |
| `docs/PHASE_C2_WRITE_AUTHZ.md` | This report |

## Behavior

| Principal | Mutations |
|-----------|-----------|
| Owner/admin | `get_pg()`, `as_owner=True` |
| Reseller | `get_pg_for_reseller`, `as_owner=False` |
| pg_staff | **Fail closed** until C5 credentials |

## Not changed

Quotas (C3) · Bot/Web shop alignment (C4) · Credential storage (C5) · Read paths (C1)

## Known limitation

pg_staff cannot create/update/delete PG resources until C5 stores their PG password/token. Owner workflow unchanged.

## Test results

```text
tests/test_phase_c0_authz.py
tests/test_phase_c1_read_isolation.py
tests/test_phase_c2_write_authz.py
tests/test_full_audit_3_8_3.py
tests/test_owner_bypass_guards.py
tests/test_security_audit_hardening.py
tests/test_wholesale_menu_qr_stats_3_3_8.py
tests/test_tenant_isolation.py

108 passed, 0 failed
```

## Rollback

Revert C2 commits on `cursor/phase-c2-write-authz-b96b`. No migrations.
