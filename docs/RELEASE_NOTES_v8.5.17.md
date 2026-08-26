# PGClockBot v8.5.17 — Release Notes

**Tag:** `v8.5.17`
**App version:** `8.5.17`
**Restore point:** tag `v8.5.16`

## Context

v8.5.16 (`100svh` + transparent `html/body/shell/main`) still left an in-page strip under the footer: `100svh` is the *small* viewport, so the document layout box (large / `100lvh`) showed `--background` below the shell. User-confirmed screenshots measured that strip as `#09090b`, not Safari chrome.

## Fixes

1. **Footer / bottom bar**
   - Mobile `.shell` fills **`100lvh`** (`100vh` fallback), `max-height: none` (overrides desktop `100dvh` cap).
   - `html:has(.shell)` locked to `100lvh` + `overflow: hidden`.
   - Open sidebar: `top` + **`bottom: 0`** (no svh/dvh height cap).
   - Closed drawer still collapses to `height: 0` (from v8.5.16) so Safari 26 does not sample it.
   - Removed the v8.5.16 transparent-shell override (it made the leftover look like a solid black hole).
   - Login `.auth-wrap` uses `100lvh` so the same gap cannot appear on the sign-in page.
   - `overscroll-behavior-y: contain` on `.main` / `.side`.

2. **Kept from v8.5.16**
   - Users table tags + boxed service menu
   - Inbox action items vertically centered

3. Service worker cache **`pgclock-shell-v7`**.

## Deploy

In-panel update to **8.5.17**. Hard-refresh Safari once so `panel.css?v=8.5.17` and SW v7 load.
