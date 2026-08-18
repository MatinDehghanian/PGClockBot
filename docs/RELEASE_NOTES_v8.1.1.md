# PGClockBot v8.1.1 — Release Notes

**Tag:** `v8.1.1`  
**App version:** `8.1.1`  
**Restore point:** tag `v8.1.0`

---

## Quota client isolation

- Create-user, plan save, and shop-delivery quota gates use the **actor’s own** PasarGuard client.
- Representative / pg_staff / Principal login and self-operations stay on stored credentials. Missing credentials fail closed.
- A client authenticated as a different username cannot supply another admin’s limits.

Owner `get_pg()` remains only for **Owner acting on a child**: create/delete admin, sell/raise capacity. That path is not mixed into the child’s session.

## Deploy

In-panel update to `8.1.1` (no new migration vs `v8.1.0`). Hard-refresh the panel after update.
