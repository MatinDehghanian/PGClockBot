# PGClockBot v5.2.6 — Release Notes

**Tag:** `v5.2.6`  
**App version:** `5.2.6`

---

## Why this release

Patch cascade v5.2.3–v5.2.5 fixed real crashes, but left a soft fail-soft layer that could **fake «قطع»** on some servers and hide template bugs. Backup restore also lacked the same progress/restart contract as panel update. This release hardens contracts for multi-server installs instead of stacking more band-aids.

## Reliability (dashboard)

- Data build is fail-soft; **render stays outside** so Jinja/KeyError still produce a diagnosable `ref=` 500.
- Degraded shell uses **unchecked** Bot/PG/Nodes + a «بارگذاری ناقص» banner — never invents «قطع».
- Session rollback on more PAYG risk catch paths.
- Regression tests lock `ac.entries` and the no-fake-disconnect contract.

## Backup restore (like update)

- After confirm: progress bar + step list (validate → safety → DB → files → env → restart → done).
- Async restore thread; poll `/backup/status` with `percent` / `awaiting_restart` / `pre_boot_id`.
- `restart_required` when auto-restart is unavailable (manual `systemctl` message).
- Locked status writes; validate failures finish as `error` (no zombie `running`).
- Block a second start while awaiting restart; `resolve_stale` on settings load; clear on `?ok=`.
- Progressive enhancement: JSON for fetch UI, 303 for classic form; `POST /backup/clear`.

## Deploy

Deploy `v5.2.6` (or in-panel update). Hard-refresh `/home` and settings → backup. Connection badges should match real probes; restore should show progress and a success flash like update.
