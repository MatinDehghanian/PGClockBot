# Phase D — Planning Only (Identity & Admin UX Unification)

**Status:** PLANNING — **no implementation** until explicit approval  
**Depends on:** Phase C production acceptance (`docs/PHASE_C_PRODUCTION_ACCEPTANCE.md`) — green with ops notes  
**Branch (docs):** `cursor/phase-c-acceptance-phase-d-plan-b96b`

---

## Goal

Unify how Owner-created secondary principals are represented and operated so that:

- Creating / editing Admin, Sub-admin, Reseller, and pg_staff is one coherent Owner workflow.  
- Credential sync, role assignment, and panel access are visible and intentional.  
- Identity gaps left by Phase C (orphaned `grant_web_access` UI, Owner vs platform Admin indistinguishability) are closed without weakening fail-closed authz.

---

## Problems Phase C intentionally left open

| ID | Gap | Risk if ignored |
|----|-----|-----------------|
| D1 | Owner «اعطای دسترسی وب» creates **reseller**, while `grant_web_access` (bare pg_staff + enc) has **no HTTP route** | Operators cannot create PG-only staff from UI; service vs product drift |
| D2 | Legacy `PgStaffAccess` remount path is «upgrade to reseller» | Converting staff may be heavier than needed; blank password upgrade leaves null enc |
| D3 | No Owner UI badge for missing `pg_credentials_ready` | Silent overview-only accounts |
| D4 | Deep-link PG pages allowed when menu clamped | Confusing empty pages vs hard deny |
| D5 | Session `role=admin` conflates Owner and platform Admin | Hard to gate Owner-only ops |
| D6 | Sub-admin not a first-class DB role | Product language ≠ storage |
| D7 | Bot has no PG capability surface for reseller/pg_staff | Web≠Bot for PG tools (accepted in C4) |
| D8 | Create-admin may silently drop `role_id` on PG API failure | Role not actually applied |

---

## Proposed Phase D scope (draft slices)

Do **not** start coding until this plan is approved and sliced.

### D0 — Inventory & product decision (analysis)

Decide binding product rules:

1. Is bare **pg_staff** (PG menus, no shop) still a supported principal, or is every secondary web user a **reseller**?  
2. If both: Owner UI must expose **two grant paths** (shop plan vs PG-only).  
3. Owner vs platform Admin: distinguish in session or keep collapsed?

**Deliverable:** short decision memo; no schema change yet.

### D1 — Owner admin lifecycle UI

Wire Owner flows to the correct service:

- PG-only grant → `grant_web_access` / `update_web_access` (enc required).  
- Shop grant → existing `provision_existing_pg_admin` (password required when enc missing).  
- Show credential status on `/pg/admins` (`missing` / `ready`).  
- Refuse blank-password upgrade when enc is null.

### D2 — Identity model (optional / larger)

Only if D0 chooses first-class Sub-admin:

- DB role or flag; migration plan; session principal kinds already in `authz.PrincipalKind`.  
- Avoid breaking existing `admin` / `reseller` / `pg_staff` cookies.

### D3 — Hard deny for clamped menus (optional)

Align `require_pg_perm` with `effective_pg_menu_keys` when credentials missing (403/redirect), not only empty lists.

### D4 — Bot PG parity (optional)

If product wants Bot PG tools for reseller/pg_staff: reuse `AuthzContext` PG decisions; same client selection as Web. Explicitly out of scope unless approved.

### D5 — Create-admin role integrity

Never silently drop `role_id`; surface PasarGuard errors; verify role read-back.

---

## Non-goals (Phase D)

- Reopening Owner-fallback for staff/reseller.  
- Reworking shop ACL semantics from C4.  
- Quota formula changes from C3.  
- CSP / billing / unrelated UX.

---

## Dependencies & risks

| Risk | Mitigation |
|------|------------|
| Converting all staff → reseller surprises shops | D0 decision + migration checklist |
| Dual grant UI complexity | Default one path; hide advanced |
| Distinguishing Owner session | Prefer config/env Owner identity over new DB table initially |
| Bot PG expansion attack surface | Feature-flag; exact action guards already in authz |

---

## Suggested acceptance criteria (when implementing later)

- [ ] Owner can create PG-only staff **or** shop reseller deliberately from UI.  
- [ ] Every active secondary principal with PG data access has decryptable enc password.  
- [ ] Admin list shows credential readiness.  
- [ ] No Owner-token path for restricted principals (regression suite green).  
- [ ] Legacy migration doc updated with the chosen product path.  
- [ ] Phase C tests remain green; new D* tests added.

---

## Immediate next step

**Await approval of D0 product decisions** before any Phase D implementation branch.

---

## Stop

This document is planning only. **Do not implement Phase D from this pass.**
