# PGClockBot v8.5.20 — Release Notes

**Tag:** `v8.5.20`
**App version:** `8.5.20`
**Restore point:** tag `v8.5.19`

## Context

v8.5.19 inset the open sidebar and page by `--safari-overlay: 100lvh − 100svh`. On iOS 26 that difference is huge, so the drawer and cards stopped far above the Safari bar (user screenshot). Intermittent blank/unstyled loads (duplicate logos, system fonts, empty page) came from the service worker calling `clients.claim()` mid-load (aborting CSS/font) and cache-first `/static/fonts/*`.

## Fixes

1. **Geometry back to v8.5.17 (user-confirmed fill)**
   - No `--safari-overlay`. Sidebar `bottom: 0`. Main padding is only `--page-title-gap` + safe-area.
   - `html/body/.shell` still `100lvh` + `overflow: hidden` so there is no leftover strip below the shell.

2. **Keep PWA-like scroll (no URL-bar jitter)**
   - `.main` is the only scroller. `.main::after { flex: 0 0 1px }` for short-page bounce.

3. **CSS / font load**
   - Stop `clients.claim()` so a new SW cannot abort in-flight `panel.css` / fonts.
   - Network-first for `fonts.css` and `/static/fonts/*`; only cache `ok` responses.
   - SW cache **`pgclock-shell-v10`**.

4. Kept users table tags, boxed service menu, inbox vertical centering, closed drawer `height: 0`.

## Deploy

In-panel update to **8.5.20**. Hard-refresh Safari once so `panel.css?v=8.5.20` and SW v10 load.
