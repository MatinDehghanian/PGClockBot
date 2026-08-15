# PGClockBot v6.1.8 — Release Notes

**Tag:** `v6.1.8`  
**App version:** `6.1.8`

---

## PG overview — node tiles

- Under PG host CPU/RAM gauges: aggregate **live** upload/download rate across all nodes
  (`incoming_bandwidth_speed` / `outgoing_bandwidth_speed` from PasarGuard realtime).
- Per-node tiles (no % rings): CPU, RAM, cumulative up/down traffic, live up/down rate.
- Unified mild poll (~5s) of `/pg/metrics` (pauses when the tab is hidden).

## Security

- `/pg/metrics` remains **PG owner principal only** (403 for reseller/pg_staff).
- Poll JSON is a whitelist (host gauges + live texts + lean node cards) — no raw
  PasarGuard system/node dumps, certs, or API keys.
- Fail-soft if system/realtime APIs error; missing fields show «—».

## Deploy

In-panel update to `6.1.8` (or deploy this tag). Hard-refresh the panel.
