# PGClockBot v8.5.8 — Release Notes

**Tag:** `v8.5.8`
**App version:** `8.5.8`
**Restore point:** tag `v8.5.7`

## Fixes

1. **Mobile "black bar" — definitive layout fix**
   - Root: even after v8.5.6/v8.5.7 `--vvh` resampling, mobile `.shell` still sized itself with `height: var(--vvh)` / `100dvh`. On some iOS/Android PWAs that value still overshot the visible fold on first paint; `html/body` background (`#09090b`) showed through as a persistent strip below the footer, and sticky-footer math pushed the footer above/below where it belonged. Opening the sidebar or scrolling temporarily hid it by forcing a relayout.
   - Fix: on `max-width: 900px`, `.shell` is now `position: fixed; inset: 0` (viewport-pinned, no height-unit timing), `html:has(.shell)` / `body` get `overflow: hidden` so only `.main` scrolls, `--vvh` prefers `window.innerHeight` (not `visualViewport.height`, which could overshoot), and the post-load scroll nudge now works on short pages too (temporarily grows `.main` by 1px when it has no overflow so Android PWA gesture-bar repaint still triggers).
   - Regression tests: `tests/test_mobile_viewport_shell_fix.py`.

2. **Users table — service picker polish**
   - Plan select control is vertically centered in its row (`flex` wrap + `margin-top: 0` on `.ui-select`).
   - Dropdown menu shows an orange alert dot next to each plan that has an active alert (`data-alert` on `<option>` → dot in boxed menu row).
   - Removed the orange cell tint (`.has-svc-alert` background) — alert is dot-only, on the toggle and in the menu.
   - Expiry column shows days only (`5 روز`, `منقضی`) — no calendar date prefix.

## Deploy

In-panel update to `8.5.8` (no new migration). Hard-refresh after update.
