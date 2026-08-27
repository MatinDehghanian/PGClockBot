# v8.5.32 — Shared geometry root cause (html fixed containing block)

Forensic fix. No `--vvh` / `100dvh` ping-pong / nested `.main` scroll / fixed footer.

## ROOT CAUSE

**One shared cause** for short-page footer gap **and** sidebar gap on iOS PWA/Safari:

1. Global `html, body { overflow-x: hidden }`
2. CSS axis coupling: `overflow-x: hidden` + `overflow-y: visible` → **computed `overflow-y: auto`**
3. WebKit: non-visible overflow on `html` → `html` becomes the **fixed containing block**
4. Short pages: `html { height: 100% }` + body flex fill → `.shell` **and** `position:fixed` `.side`/`.backdrop` pin to that html box
5. If html box ≠ visible viewport → **same gap** under page and under sidebar
6. Long pages mask the mismatch via scroll — looks fine

Not two bugs. Not “Safari padding”. Not safe-area alone.

## MINIMAL FIX

- `html:has(.shell)` → `overflow-x: visible; overflow-y: visible` (override global on **both** axes)
- `body` alone → `overflow-y: auto` + `overflow-x: hidden`
- Drawer open: **no** `overflow: hidden` on html/body (only `touch-action` / `overscroll-behavior`)
- Keep document-scroll, flex short-page fill, unified foot-gap+safe-bottom, `right`-based sidebar (no transform)

## After update

Hard refresh + Clear Website Data. SW: `pgclock-shell-v22`. Restore: `v8.5.31`.

**Note:** Real iPhone Safari/PWA is **not** available in CI. Chromium proves overflow coupling + shared CB mechanism (transform analog) + live geometry invariants. Confirm on device: Notifications (short) + a long page, Safari + PWA, sidebar open/closed.
