# PGClockBot v5.1.1 — Release Notes

**Tag:** `v5.1.1`  
**App version:** `5.1.1` (`VERSION` + `app/version.py`)  
**Base:** `v5.1.0` (UX20)

---

## Highlights

Patch release on top of v5.1.0:

- Fix Internal Server Error on bot settings and web-panel settings (UnboundLocalError from a shadowed `get_all_settings` import in the backup tab)
- Consolidate gift codes, magic links, purchase steps, and settings export/import under `/tools` with sidebar entry and internal tabs
- Move PasarGuard quick-open to `/pg` stats box only (removed from `/home`)
- Rename purchase funnel to **مراحل خرید**; show summary at the bottom of the dashboard
- Remove gift-code and settings-export shortcuts from the home quick-links

## Database

No new Alembic revision. Still requires `0009_ux20_ops_features` from v5.1.0.

## Ops notes

1. Backup: `pgclock backup --note "pre-v5.1.1"`.
2. Deploy `main` / tag `v5.1.1` (ensure `VERSION` reads `5.1.1`).
3. Restart panel; open `/settings` and `/settings?tab=backup` to confirm settings load.
4. Open `/tools` from the bot sidebar to verify the tools hub.
