# PGClockBot v7.6.1 — Release Notes

**Tag:** `v7.6.1`  
**App version:** `7.6.1`  
**Restore point:** tag `v7.6.0` (v7.6.0)

---

## Speed

- In-app navigation no longer hides arrived HTML behind the page skeleton.
- Skeleton appears only on the departing page if the next response takes longer than 150ms.
- Removed the 380ms fade-in that ran after every sidebar click (`page-was-slow`).

## Deploy

In-panel update to `7.6.1` (no new migration). Hard-refresh the panel after update.
