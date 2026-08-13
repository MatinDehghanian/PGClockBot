# PGClockBot v5.2.14 — Release Notes

**Tag:** `v5.2.14`  
**App version:** `5.2.14`

---

## UI — Home dashboard

- First content row: side-by-side overview portals — **orange** → bot overview (`/dashboard`), **blue** → PasarGuard (`/pg`); stay side-by-side on mobile.
- Period sales card: today / 7 days / 30 days (Asia/Tehran calendar) with orders, delivered, revenue, new users (shop-scoped).
- Work queue (action center) below periods, with empty state when idle.
- CPU/RAM gauges and connection badges unchanged. Dual `home-panel-*` blocks and funnel removed from `/home`.

Shared `_home_ops.html` for admin and reseller homes.

## Deploy

In-panel update to `5.2.14` (or deploy this tag). Hard-refresh the panel.
