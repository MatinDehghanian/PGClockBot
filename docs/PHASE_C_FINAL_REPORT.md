# Phase C — Final Report (C0–C5)

**Status:** Complete through C5 — **production acceptance green** (see `PHASE_C_PRODUCTION_ACCEPTANCE.md`)  
**Baseline:** Phase B tip + C0–C5 on sequential feature branches

---

## Outcome

Authorization is centralized (`authz.py`), tenant-safe for PasarGuard reads/writes, quota-aware (incl. HWID), Bot/Web shop ACL aligned, and pg_staff uses **own** encrypted PG credentials when stored.

| Phase | PR / branch theme | Result |
|-------|-------------------|--------|
| Analysis | permission architecture doc | Approved (#134) |
| C0 | Unified decision layer | Green (#135) |
| C1 | Read isolation | Green (#136) |
| C2 | Write fail-closed | Green (#137) |
| C3 | HWID / RoleLimits parity | Green (#138) |
| C4 | Bot/Web shop alignment | Green (#139) |
| C5 | pg_staff credential sync | Green (#140) |
| Acceptance | Production-safety verify (no code) | Green — docs pass |

## Role matrix (post-C5)

| Role | Shop | PG menus | PG client |
|------|------|----------|-----------|
| Owner / platform Admin | Full | Full | Owner `get_pg()` |
| Reseller | `web_permissions` (Bot=Web) | Role-mapped when linked | `get_pg_for_reseller` |
| pg_staff | None | Role-mapped; overview-only until credentials | `get_pg_for_staff` or fail closed |

## Invariants held

- No Owner fallback for reseller/pg_staff operations.  
- No credential mixing into C4.  
- Additive schema only (`pg_admin_password_enc`, `pg_role_id` on `pg_staff_access`).  
- Owner `modify_admin` only for password sync on grant/edit.

## Ops follow-ups

- Legacy staff remediation: `docs/PHASE_C_LEGACY_MIGRATION.md`  
- Phase D planning (identity / Owner UI): `docs/PHASE_D_PLAN.md` — **not implemented**

## Out of scope (Phase D+)

- First-class Sub-admin DB role  
- Broader identity unification / Owner grant UI for bare pg_staff  
- Bot PG surface for reseller/pg_staff (still platform-admin only on Bot)
