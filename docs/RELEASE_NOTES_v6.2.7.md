# PGClockBot v6.2.7 — Release Notes

**Tag:** `v6.2.7`  
**App version:** `6.2.7`

---

## Fixes

### Page skeleton (no load delay)

- Skeleton shows only on in-app link/form navigation while waiting for the next page.
- Reveal is immediate when DOM is ready — no forced minimum delay / no content hide on hard refresh.

### PG overview spacing

- Node board → footer gap matches the rest of the panel (script moved out of `main-body`; panels hug content).

## Deploy

In-panel update to `6.2.7` (no new migration). Hard-refresh after update.
