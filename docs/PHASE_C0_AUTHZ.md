# Phase C0 — Permission Architecture Foundation

**Status:** Implemented  
**Branch:** `cursor/phase-c0-authz-foundation-b96b`  
**Scope:** Single authorization decision layer only (behavior-preserving)

---

## What changed

| File | Change |
|------|--------|
| `app/services/authz.py` | **New** — `AuthzContext`, `can_shop` / `can_pg_page` / `can_pg_action` / `can_pg_user_action` |
| `app/api/app.py` | `require_perm` / `require_pg_perm` call authz |
| `app/services/resellers.py` | `has_perm` delegates to authz |
| `app/services/pg_access.py` | `staff_pg_*` delegates to authz |
| `tests/test_phase_c0_authz.py` | Parity + fail-closed tests |
| `docs/PHASE_C0_PLAN.md` | Plan (approved) |
| `docs/PHASE_C0_AUTHZ.md` | This report |

## What did **not** change

- Owner / platform admin session model (`role=="admin"` full bypass)
- PasarGuard client selection (`_staff_pg`, `get_pg`, `get_pg_for_reseller`)
- Database schema / Alembic
- UI templates / bot keyboards
- Quota / limits
- Read isolation / write authorization (C1+)

## Decision API

```text
authz_from_staff(staff) → AuthzContext
can_shop(ctx, key)
can_pg_page(ctx, key)
can_pg_action(ctx, resource, action)   # fail closed if matrix missing
can_pg_user_action(ctx, action)
```

## Rollback

Revert the C0 commit(s). No migrations. Authz is additive; wrappers can be restored to prior inline checks from git history.

## Acceptance criteria

- [x] Single decision module exists
- [x] Web deps + Bot helpers use it
- [x] No intentional UX / PG op / Owner / DB changes
- [x] No database / Alembic changes
- [x] Parity tests green

## Test results (local)

```text
tests/test_phase_c0_authz.py
tests/test_security_audit_hardening.py
tests/test_production_audit_3_5_6.py::HasPermEmptyAclTests
tests/test_owner_bypass_guards.py
tests/test_tenant_isolation.py
tests/test_shop_isolation_3_5_4.py
tests/test_unified_auth_reply_menu_3_5_5.py

76 passed, 0 failed
```

Parity verified: old shop/PG allow-deny matrix == `can_shop` / `can_pg_page` / `can_pg_action`.
