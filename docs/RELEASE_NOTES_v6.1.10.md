# PGClockBot v6.1.10 — Release Notes

**Tag:** `v6.1.10`  
**App version:** `6.1.10`

---

## PG overview design

- Live upload/download rate tiles: large number + smaller unit (`کیلوبایت/ثانیه`, …).
- Node board is full-width inside the same `home-panels` column as panel stats.
- Per-node tiles: CPU/RAM progress meters with percent on the bar; core count and
  RAM amount beside titles; each metric in an inner box; same num/unit hierarchy
  for traffic and live rates.

## Security

- Unchanged owner-only `/pg/metrics` whitelist (parts instead of raw dumps).

## Deploy

In-panel update to `6.1.10` (or deploy this tag). Hard-refresh the panel.
