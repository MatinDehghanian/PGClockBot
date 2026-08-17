# PGClockBot v7.5.0 — Release Notes

**Tag:** `v7.5.0`  
**App version:** `7.5.0`  
**Restore point:** tag `v7.0.6` (v7.0.6)

---

## نمایندگان سازمان

- Web login for org reps uses the same PasarGuard username and password (`pg_staff` contract). Creating an L1 or L2 rep attaches that panel login immediately; the client cannot post a different username.
- `/principals` is labeled **نمایندگان من** / **افزودن نماینده**. Level 1/2 labels are off the product UI. Owner still has shop **نمایندگان** at `/resellers` (not merged in this release).
- Hierarchy, authz engine, max depth (Owner → L1 → L2), and `get_pg()` isolation are unchanged. Tag `v7.0.0` was not moved.

## Deploy

In-panel update to `7.5.0` (no new migration). Hard-refresh the panel after update.
