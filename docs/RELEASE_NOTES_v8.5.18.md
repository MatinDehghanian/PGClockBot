# PGClockBot v8.5.18 — Release Notes

**Tag:** `v8.5.18`
**App version:** `8.5.18`
**Restore point:** tag `v8.5.17`

## Context

v8.5.17 filled the layout viewport (`100lvh`) but locked `html/body` with `overflow: hidden` and kept `.main` as a nested `overflow-y: auto` scroller. Two user-visible bugs followed:

1. **No rubber-band on short pages** — iOS does not bounce a nested scroller unless its content overflows, and `overflow: hidden` on the document disabled root bounce entirely.
2. **Solid slab above Safari’s floating chrome** — a non-scrollable document makes Safari keep an expanded, opaque toolbar. The flex footer sat at the `100lvh` bottom (behind that chrome), so the visible gap between cards and the bar was empty `--background`.

## Fixes

1. **Spring scroll**
   - Document is the scroller (`overflow-y: auto` on `html:has(.shell)`).
   - `.main` / `.shell` use `overflow: visible` so a short page is not trapped in a non-overflowing nested box.
   - Sidebar keeps `overscroll-behavior-y: contain`.

2. **Automatic full-screen at every size / toolbar state**
   - Shell / html / body `min-height: max(100vh, 100lvh)` so the canvas paints under the overlay.
   - `--safari-overlay: max(0px, 100lvh - 100dvh)` — expanded toolbar → inset; collapsed toolbar / PWA → `0`. Applied to `.main` and open `.side` padding-bottom (and login `.auth-wrap`).
   - No `--vvh`, no `visualViewport` JS, no transparent-shell hack.

3. **Kept from v8.5.16 / v8.5.17**
   - Users table tags + boxed service menu
   - Inbox action items vertically centered
   - Closed drawer `height: 0`

4. Service worker cache **`pgclock-shell-v8`**.

## Deploy

In-panel update to **8.5.18**. Hard-refresh Safari once so `panel.css?v=8.5.18` and SW v8 load.
