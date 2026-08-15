# PGClockBot v6.1.7 — Release Notes

**Tag:** `v6.1.7`  
**App version:** `6.1.7`

---

## Overview metrics & UI

- CPU/RAM gauges moved off `/home` onto bot overview (`/dashboard`, local host)
  and PasarGuard overview (`/pg`, remote `/api/system`).
- Quick-access blocks removed from bot and PG overviews.
- Button-colors section heads are title+caption only (no accent boxes).
- Table ID/`#` columns compacted panel-wide (`col-id`).

## Security

- `/dashboard/metrics` — platform admin only.
- `/pg/metrics` — PG owner principal only (403 for reseller/pg_staff).

## Deploy

In-panel update to `6.1.7` (or deploy this tag). Hard-refresh the panel.
