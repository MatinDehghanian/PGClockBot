# PGClockBot v8.5.9 — Release Notes

**Tag:** `v8.5.9`
**App version:** `8.5.9`
**Restore point:** tag `v8.5.8`

## Fixes

1. **Mobile black bar + page-enter jitter — actual root cause**
   - v8.5.8 pinned `.shell` with `position: fixed; inset: 0` but **did not override** desktop `.main { height: 100%; max-height: var(--vvh) }`. On mobile, `--vvh` is the full viewport while `.shell`'s content box is shorter (topbar padding + safe area). `.main` therefore extended past the shell bottom → persistent near-black strip under the footer. The scroll **nudge** loop (6× over ~1s, 2px scroll + temporary `minHeight` bump) caused the visible **shake on every page enter**.
   - Fix: mobile `.main` now uses `height: auto; max-height: none; flex: 1 1 0; min-height: 0` (exact fill of remaining shell space). `html/body` use `position: fixed; inset: 0` (iOS/PWA safe). Safe-area bottom padding moved to `.shell` (not duplicated on `.main`). Removed scroll nudge entirely and removed the 12× `--vvh` resample loop + `visualViewport` scroll listener.

## Deploy

In-panel update to `8.5.9` (no new migration). Hard-refresh after update — critical for cached `panel.js`.
