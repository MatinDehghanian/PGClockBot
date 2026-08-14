# PGClockBot v6.1.4 — Release Notes

**Tag:** `v6.1.4`  
**App version:** `6.1.4`

---

## Rollback

Restores panel viewport / footer / sidebar behavior to **v6.1.1**, undoing the
v6.1.2 (`svh`) and v6.1.3 (`--vh` JS) experiments that caused short-page layout
regressions for some installs.

Tree restored from branch `cursor/restore-before-viewport-svh-5b2d` @ `54a0736`,
then republished as **6.1.4** so panels already on 6.1.2 / 6.1.3 can update
forward to this rollback.

## Deploy

In-panel update to `6.1.4` (or deploy this tag). Hard-refresh the panel.
