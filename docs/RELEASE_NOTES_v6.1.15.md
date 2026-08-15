# PGClockBot v6.1.15 — Release Notes

**Tag:** `v6.1.15`  
**App version:** `6.1.15`

---

## Fix

- Traffic rates: fundamental RTL fix. Previous patches forced `dir=ltr` on the
  whole value, which put the unit at the right edge so RTL readers saw
  «کیلوبایت/ثانیه ۲۰۰». Now uses the panel `.byte-size` principle — number on
  the visual right, unit on the left — so it reads as «۲۰۰ کیلوبایت/ثانیه».

## Deploy

In-panel update to `6.1.15` (or deploy this tag). Hard-refresh the panel
(Ctrl+Shift+R) so `panel.css` is not cached.
