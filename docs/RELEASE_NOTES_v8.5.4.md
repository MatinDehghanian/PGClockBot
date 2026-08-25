# PGClockBot v8.5.4 — Release Notes

**Tag:** `v8.5.4`  
**App version:** `8.5.4`  
**Restore point:** tag `v8.5.3`

## Fixes

1. **Black bar at bottom (esp. with sidebar open)**
   - Root: mobile `.side` used `height: calc(100dvh − topbar)` which often fell short of the real screen bottom, exposing near-black `body` background
   - Fix: `top` + `bottom: 0` + `height: auto` (same as backdrop); `body.nav-open` paints `var(--bg-card)`

2. **Users table on mobile (match other panel tables)**
   - Secondary columns (telegram / service / volume / expiry / wallet) use `col-hide-sm`
   - Mobile shows: **name · status · actions**, with service · volume · expiry stacked under the name (`.cell-name-meta`)
   - Role / risk chips use normal `.badge` size (removed 9px shrink)

## Deploy

In-panel update to `8.5.4` (no new migration). Hard-refresh after update.
