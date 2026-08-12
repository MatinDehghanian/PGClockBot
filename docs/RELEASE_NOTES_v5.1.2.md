# PGClockBot v5.1.2 — Release Notes

**Tag:** `v5.1.2`  
**App version:** `5.1.2` (`VERSION` + `app/version.py`)  
**Base:** `v5.1.1`

---

## Highlights

- **Dashboard Internal Error fix (root cause):** Jinja `| num` crashed on missing attributes (`Undefined`). Hardened `format_number` so panel filters never raise. Optional UX widgets on `/home` (action center, funnel, PG health) are isolated so a failure cannot 500 the whole dashboard.
- **Telegram button styles (sparse):** Bot API `style` on critical actions only — approve=`success`, reject/delete confirm=`danger`, buy/renew/force-join check=`primary`. Main reply menus stay uncolored.

## Ops notes

1. Backup: `pgclock backup --note "pre-v5.1.2"`.
2. Deploy `main` / tag `v5.1.2`.
3. Open `/home` — should load even if funnel tables/widgets fail.
4. Telegram clients older than Feb 2026 ignore button styles (buttons still work).
