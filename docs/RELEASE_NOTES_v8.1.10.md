# PGClockBot v8.1.10 — Release Notes

**Tag:** `v8.1.10`  
**App version:** `8.1.10`  
**Restore point:** branch `cursor/restore-before-pg-shell-first-ffcf` / tag `restore/pre-pg-shell-first-v8.1.9` (@ `v8.1.9`)

---

## Panel `/pg` shell-first

- After `require_pg_perm("pg_overview")`, `/pg` returns fast chrome (title, ticket alert, remediation) plus a loading placeholder.
- Decorative widgets load from `/pg/body` with the **same** server permission.
- Live-metrics script stays outside swapped content, re-queries the DOM each tick, and listens for `panel-widgets-ready`.
- Escape hatch: `/pg?full=1`. No SPA / `panelNavigate`. Auth/ACL untouched.

## Deploy

In-panel update to `8.1.10` (no new migration vs `v8.1.9`). Hard-refresh the panel after update.
