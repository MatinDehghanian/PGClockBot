# PGClockBot v5.2.3 — Release Notes

**Tag:** `v5.2.3`  
**App version:** `5.2.3`

---

## Critical fix — dashboard / login Internal Server Error

Root causes addressed (especially for platform admins):

1. **Poisoned SQLAlchemy session:** caught failures (sidebar unread, funnel, settings, …) left the shared request session in `PendingRollbackError`, so later `/home` / `/dashboard` queries 500’d. Every catch path now rolls back quietly.
2. **Unwrapped `build_home_overview`:** any single failing sub-task (DB / PG / metrics) aborted the whole page. Now uses `return_exceptions` + fail-soft defaults so `home.html` always gets a complete `overview` shell.
3. **Jinja gauge trap:** `host.cpu_percent is not none` is true for `Undefined`, then `'%.0f'|format(...)` raised. Gauges now use `is number`.
4. **Corrupt `web_admin.json`:** parse errors no longer 500 login / session version checks (fail closed → empty password / empty `sv`).
5. **PG capability probe:** `enrich_platform_admin_staff` never raises; Owner keeps shop panel with empty PG ACL on probe failure.
6. **Safe generic 500 page:** Persian message only — no traceback, cookies, tokens, or paths leaked to the client (details stay in server logs).

## Deploy

1. Backup as usual.
2. Deploy `main` / tag `v5.2.3`.
3. Hard-refresh is optional (panel already sends `Cache-Control: no-store`).
4. If an admin still cannot log in after a previously corrupt `web_admin.json`, reset credentials via the normal repair path / wizard — the panel will no longer 500 on that file.
