# PGClockBot v8.1.11 — Release Notes

**Tag:** `v8.1.11`  
**App version:** `8.1.11`  
**Restore point:** branch `cursor/restore-before-loading-polish-paginate-ffcf` / tag `restore/pre-loading-polish-paginate-v8.1.10` (@ `v8.1.10`)

---

## Panel loading polish

- `/pg` shell-first loading uses a centered design-token spinner (title + caption) instead of plain muted text.
- Shared partial `_panel_widgets_loading.html` + CSS aligned with existing panel motion/tokens.

## `/pg/users` pagination

- Fetches 50 users per page (`?page=`) instead of a flat 200-row window.
- Prev/next pager preserves search `q`.
- When ownership/search shrinks the API window, claimed totals are cleared (same idea as bot scoped lists).
- Auth/ACL and `require_pg_perm("pg_users")` unchanged.

## Deploy

In-panel update to `8.1.11` (no new migration vs `v8.1.10`). Hard-refresh the panel after update.
