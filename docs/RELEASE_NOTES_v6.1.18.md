# PGClockBot v6.1.18 — Release Notes

**Tag:** `v6.1.18`  
**App version:** `6.1.18`

Includes **v6.1.17** + **v6.1.18**.

---

## Fix (6.1.18)

- Page-head action buttons (opposite the title — one or two) now hug their
  label width like «افزودن نماینده»: same horizontal text padding
  (`padding-inline: var(--space-2)`), no equal-column / full-row stretch on
  mobile that made short labels look oversized.

## Fix (6.1.17)

- Node boxes: CPU cores, RAM used/total, upload/download totals, and rates all
  use the panel `.byte-size` RTL placement — number on the visual right, unit on
  the left (reads as «4 هسته», «2.0 / 8.0 گیگ», «200 کیلوبایت/ثانیه»).
- Removed the forced `dir=ltr` meta / `row-reverse` approach that put Persian
  units on the wrong edge for cores and RAM.

## Deploy

In-panel update to `6.1.18`. Hard-refresh (`Ctrl+Shift+R`) so `panel.css`
cache clears.
