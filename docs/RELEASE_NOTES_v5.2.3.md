# PGClockBot v5.2.3 — Release Notes

**Tag:** `v5.2.3`  
**App version:** `5.2.3`

---

## Critical fix — Internal Server Error after «رفتار کاربر» / UX pack

Symptoms (intermittent, often platform admins, also other roles): 500 on login redirect, `/home`, `/finance?tab=behavior`, sometimes after logout re-entry. Browser cache clear did not help (server-side).

### Root causes

1. **Poisoned SQLAlchemy session** — a caught DB error (sidebar unread, funnel, receipt match, …) left the shared request session in `PendingRollbackError`; later queries on the same request 500’d.
2. **Unwrapped overview / finance funnel / delivery** — one failing UX20 widget aborted the whole page.
3. **Jinja gauge trap** — `is not none` is true for `Undefined`, then `'%.0f'|format(...)` raised.
4. **Corrupt `web_admin.json` / PG probe raise** — admin-only login/session 500s.

### Hardening in this release (all roles)

- `rollback_quiet` + `recover_session` after `require_staff` and on every catch path for home / finance / dashboard widgets.
- `build_home_overview` fail-soft (`return_exceptions` + complete shell).
- Finance **behavior** tab uses `_safe_funnel` (same as dashboard); **delivery** tab isolated.
- Reseller `/home` profile/stats/tickets/billing/PG isolated.
- Gauges use `is number` (admin CPU/RAM + PG quota).
- Safe generic HTML/JSON 500 — no traceback/secrets to the client.
- `get_db` rolls back on uncaught route errors before re-raise.

## Deploy

1. Backup as usual.
2. Deploy `main` / tag `v5.2.3`.
3. Panel already sends `Cache-Control: no-store` — hard refresh optional.
4. Re-test as platform admin, reseller, and pg_staff: login → `/home` → `/finance?tab=behavior` → logout → login.
