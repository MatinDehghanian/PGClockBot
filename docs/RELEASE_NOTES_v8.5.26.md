# v8.5.26 — mobile bottom gap root fix

## Problem

v8.5.17–v8.5.25 iterated on viewport units (`100lvh`, `100dvh`, `--vvh`, `calc(...)`) without fixing the layout bleed: desktop `.main { height: 100%; max-height: 100dvh }` applied on mobile, so `.main` overshot the shell content box (viewport − topbar − safe-bottom) by ~99px → phantom near-black strip under the footer. `safe-bottom` was also stacked on `.main` padding while the shell already filled `100dvh`.

v8.5.24's `--vvh` JS hack broke scroll/hamburger (reverted in v8.5.25).

## Fix

1. **Mobile `.main` reset** — `height: auto; max-height: none; flex: 1 1 0; min-height: 0`
2. **Single safe-area owner** — `.shell { padding-bottom: var(--safe-bottom) }`; `.main` only `var(--foot-gap)`
3. **Sidebar** — `bottom: 0; height: auto` (keep v8.5.25 `pointer-events: none` on closed drawer + hamburger fixes)
4. **No new viewport JS** — stays on v8.2.8 `100dvh` shell

## Measured (Playwright 390×844, safe-bottom=34px)

| Metric | Before | After |
|--------|--------|-------|
| `main.maxHeight` | 844px (100dvh bleed) | none |
| Footer → main bottom | 50px (16+34 stacked) | 16px (foot-gap only) |
| Main → shell bottom | 0px (overflow) | 34px (= shell safe pad) |

## After update

Hard refresh; SW cache **`pgclock-shell-v16`**. Restore: `git checkout v8.5.25`.
