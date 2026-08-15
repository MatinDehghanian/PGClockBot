# PGClockBot v6.1.16 — Release Notes

**Tag:** `v6.1.16`  
**App version:** `6.1.16`

---

## Fix

- Node metric boxes: force the same number/unit placement as live rates via
  `flex-direction: row-reverse` (number on the right, unit on the left), with
  higher specificity under `.pg-node-metric` so parent direction cannot flip it.

## Deploy

In-panel update to `6.1.16`. Hard-refresh (`Ctrl+Shift+R`) to clear CSS cache.
