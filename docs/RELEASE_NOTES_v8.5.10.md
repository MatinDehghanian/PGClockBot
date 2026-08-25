# PGClockBot v8.5.10 — Release Notes

**Tag:** `v8.5.10`
**App version:** `8.5.10`
**Restore point:** tag `v8.5.9`

## Fixes

1. **Mobile black bar on iOS (still present in v8.5.9)**
   - Symptom: a solid black dead zone (~10–15% screen height) under scrollable content; bottom cards cut off (see settings/backup page).
   - Root: v8.5.9 used `position: fixed; inset: 0` on `html/body` plus `-webkit-fill-available`. On iOS/Safari/PWA this **shrinks the layout box** so `.shell` paints shorter than the physical screen — black shows below the app.
   - Fix: remove fixed/`fill-available` on `html/body`; size mobile `.shell` with explicit `height/min-height/max-height: var(--vvh)` (not `inset:0`). `--vvh` now uses `max(innerHeight, clientHeight, visualViewport extent)` synchronously in `<head>`. Shell background extends through the home-indicator safe area; `.main` keeps `safe-bottom` padding for content.

## Deploy

In-panel update to `8.5.10` (no new migration). **Hard-refresh required** (cached `panel.css`).
