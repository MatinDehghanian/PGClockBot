# Phase C — Final Report (C0–C5)

**Status:** Complete through C5  
**Baseline:** Phase B tip + C0–C5 on sequential feature branches

---

## Outcome

Authorization is centralized (`authz.py`), tenant-safe for PasarGuard reads/writes, quota-aware (incl. HWID), Bot/Web shop ACL aligned, and pg_staff uses **own** encrypted PG credentials when granted.

| Phase | PR / branch theme | Result |
|-------|-------------------|--------|
| Analysis | permission architecture doc | Approved |
| C0 | Unified decision layer | Green |
| C1 | Read isolation | Green |
| C2 | Write fail-closed | Green |
| C3 | HWID / RoleLimits parity | Green |
| C4 | Bot/Web shop alignment | Green |
| C5 | pg_staff credential sync | This branch |

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

## Out of scope (Phase D+)

- First-class Sub-admin DB role  
- Broader identity unification  
- Bot PG surface for reseller/pg_staff (still platform-admin only on Bot)
