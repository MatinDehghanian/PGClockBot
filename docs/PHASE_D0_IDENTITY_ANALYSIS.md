# Phase D0 — Identity Architecture Analysis

**Status:** Analysis complete — awaiting decision checklist approval  
**Parent:** `docs/PHASE_D_PLAN.md`  
**Code changes:** None

---

## Confirmed

- **pg_staff** is an independent secondary admin (PG-only).  
- Must **not** require conversion to reseller for web/PG access.  
- Phase C authz isolation remains the security baseline.

---

## Principal map (target)

| Kind | Storage | Web | Shop | PG | Bot |
|------|---------|-----|------|----|-----|
| Owner | `web_admin.json` + env `PG_*` | yes | full | owner client | `ADMIN_IDS` (separate) |
| platform Admin | same session as Owner today | yes | full | owner client | same |
| pg_staff | `PgStaffAccess` | yes | no | staff client + enc | none (web-only) |
| Reseller | `ResellerProfile` + `BotUser` | yes | yes | reseller client when linked | yes |

---

## As-is critical defect

Owner «اعطای دسترسی وب» → `provision_existing_pg_admin` → **Reseller** and may **delete** `PgStaffAccess`.

True pg_staff path `grant_web_access` exists in service layer only.

This is the primary Phase D product defect relative to the confirmed decision.

---

## Flow inventory (summary)

See full detail in `PHASE_D_PLAN.md` §1–2.

| Flow | Works for architecture? |
|------|-------------------------|
| Owner setup | Partial (web≠PG sync) |
| Create PG admin | Partial (no password policy; silent role drop) |
| Grant web (UI) | **Fail** vs pg_staff-first-class |
| `grant_web_access` service | Pass (orphaned) |
| Reseller provision | Pass for reseller intent |
| Staff password `/security` | Pass for remediating enc |
| Login/session | Pass isolation; partial readiness UX |

---

## Open decisions (must answer before D1 code)

1. **Username equality** for pg_staff: enforce `web == pg` (recommended) or allow divergence?  
2. **Owner dual credentials:** keep web and `PG_PASSWORD` separate, or optional sync when names match?  
3. **platform Admin split:** defer distinguishing Owner in session until D4?  
4. **Opt-in migrate staff→reseller:** allowed with confirmation, or never?  
5. **Password digits:** require digit in shared policy?

---

## Exit criteria for D0

- Binding answers to open decisions recorded (PR comment or checklist tick).  
- Phase D plan §9 checklist approved.  
- No implementation until then.
