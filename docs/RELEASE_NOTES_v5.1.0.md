# PGClockBot v5.1.0 — Release Notes

**Tag:** `v5.1.0`  
**App version:** `5.1.0` (`VERSION` + `app/version.py`)  
**Restore point (pre-release):** branch `cursor/restore-before-ux20-5b2d` @ `614497e` (v5.0.6)

---

## Highlights

Twenty ops/UX improvements shipped on top of v5.0.6, keeping the existing panel design language:

- Quick open PasarGuard next to overview (admin + reseller URL resolution)
- Daily action center on Home
- Live PG connection health on Home
- Failed delivery queue + retry
- Gift / charge codes, magic deep-links, purchase funnel
- Shop maintenance mode, capacity warn at 80%, plan clone
- Staff notes + risk flags, receipt match hints
- Scheduled backup + verify, nightly admin Telegram report
- One-tap renew on expiry alerts
- Settings export/import, reseller brand color, live purchase simulator

## Database

| Revision | Change |
|----------|--------|
| `0009_ux20_ops_features` | `delivery_failures`, `charge_codes`, `funnel_events`; staff notes / risk flags; renew nudge + capacity warn timestamps |

**Migrate:** `alembic upgrade head` (or `pgclock migrate`) → confirm `0009_ux20_ops_features`.

## Ops notes

1. Backup before upgrade: `pgclock backup --note "pre-v5.1.0"`.
2. Stop → migrate → start → `pgclock health`.
3. Optional: enable nightly report / scheduled backup under panel settings (notifications + backup tabs).
4. To roll back code to pre-UX20: check out `cursor/restore-before-ux20-5b2d` (still at v5.0.6). Schema rollback may need a DB restore from backup.
