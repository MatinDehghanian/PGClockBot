# PGClockBot v8.5.21 — Release Notes

**Tag:** `v8.5.21`
**App version:** `8.5.21`
**Restore point:** tag `v8.5.20`

## Summary

Replaces the v8.5.20 mobile viewport approach with the **proven v8.2.12 shell** (100dvh, inner `.main` scroll, sticky footer). Keeps v8.5.20 improvements: `--foot-gap` footer alignment, network-first fonts/panel in SW, no mid-load SW takeover.

## Root cause

v8.5.16–v8.5.20 stacked conflicting viewport hacks (`--safari-overlay`, document lock, `height:0` drawer, `100lvh`). v8.5.20 on main still used document lock + `100lvh` — user-confirmed issues persisted.

## Fix

1. Restore v8.2.12 mobile `@media` block (`100dvh` shell + sidebar calc height)
2. Remove `--safari-overlay`, html/body lock, drawer collapse
3. Keep ios-safari sampling guard (transparent shell, closed drawer `visibility:hidden`)
4. Keep `--foot-gap`, fonts network-first SW, dashboard veil 12s timeout
5. Service worker cache **`pgclock-shell-v11`**

## Deploy

1. Update to **8.5.21**
2. Clear Safari website data once (or unregister service worker)
3. Hard-refresh on iPhone Safari + Chrome
