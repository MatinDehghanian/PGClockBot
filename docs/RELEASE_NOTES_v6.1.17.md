# PGClockBot v6.1.17 — Release Notes

**Tag:** `v6.1.17`  
**App version:** `6.1.17`

---

## Fix

- Node boxes: CPU cores, RAM used/total, upload/download totals, and rates all
  use the panel `.byte-size` RTL placement — number on the visual right, unit on
  the left (reads as «4 هسته», «2.0 / 8.0 گیگ», «200 کیلوبایت/ثانیه»).
- Removed the forced `dir=ltr` meta / `row-reverse` approach that put Persian
  units on the wrong edge for cores and RAM.

## Deploy

In-panel update to `6.1.17`. Hard-refresh (`Ctrl+Shift+R`) if CSS looks cached.
