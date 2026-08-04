# Phase C3 — Limits and Quotas

**Status:** Implemented  
**Branch:** `cursor/phase-c3-limits-quotas-b96b`  
**Depends on:** C0–C2 (verified green)

---

## Scope

Enforce PasarGuard `RoleLimits` for restricted principals:

| Limit | Status |
|-------|--------|
| max users | Already present — regression covered |
| traffic / data_limit min–max | Already present — regression covered |
| expiration min–max | Already present — regression covered |
| **HWID / device min–max** | **Added** |
| Resource access allow-lists | Already in C1 filters / create gates |
| Host/node/template **count** caps | Not in PasarGuard `RoleLimits` — N/A |

## Changed files

| File | Change |
|------|--------|
| `app/services/pg_quota.py` | `_check_hwid_bounds`, `hwid_bounds`, create default-to-max |
| `app/services/provision_gate.py` | Pass `hwid_limit` / `hwid_changed` |
| `app/services/pasarguard.py` | `hwid_limit` on create/modify payloads |
| `app/api/pg_pages.py` | Parse + enforce HWID on user create/edit |
| `app/web/templates/pg_users.html` | HWID form fields |
| `tests/test_phase_c3_limits_quotas.py` | New |
| `docs/PHASE_C0_C2_VERIFICATION.md` | Prior verification |
| `docs/PHASE_C3_LIMITS_QUOTAS.md` | This report |

## Behavior

- Owner/admin: still bypasses quota gates.
- Restricted create: HWID checked; if omitted and role has `max_hwid_per_user`, defaults to that max (no unlimited-device bypass).
- Restricted modify: when HWID field submitted, bounds enforced.
- Template create path: still only max_users + write gate (PG applies template HWID).

## Not changed

Bot/Web permission alignment (C4) · Credential sync (C5) · Read/write client selection (C1/C2)

## Test results

```text
tests/test_phase_c3_limits_quotas.py
tests/test_pg_quota.py
(+ C0–C2 suites)

See commit message / CI for full count.
```

## Rollback

Revert C3 commits on `cursor/phase-c3-limits-quotas-b96b`. No migrations.
