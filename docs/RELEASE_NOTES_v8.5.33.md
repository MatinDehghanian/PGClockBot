# v8.5.33 — Real root cause: body as content-sized fixed CB

Rolls back the failed v8.5.32 html-overflow hypothesis. Keeps document scroll (no nested `.main`).

## ROOT CAUSE

**Exact element/property:** `body` with `overflow-y: auto` (explicit or via `overflow-x:hidden` axis-coupling) / `-webkit-overflow-scrolling`, while `.side` / `.side-backdrop` are descendants of `body` / `.shell`.

On WebKit this makes **body a content-sized fixed containing block**.

| | Why |
|--|--|
| Long / PWA normal | body/shell taller than viewport → `bottom:0` past the fold → no visible gap |
| Short / PWA short | body/shell ≈ fill height → drawer tracks that box → **page gap + sidebar gap together** |
| Why v8.5.32 failed | `html` height is **identical** short vs long (`height:100%`); first differing ancestors are `.shell`/`body`. v8.5.32 kept `body { overflow-y:auto }` |

## MINIMAL FIX

- `html` + `body`: `overflow-x/y: visible` (override global `overflow-x:hidden`)
- Viewport is the only vertical scroll owner
Horizontal clip: `.main { overflow-x: clip }` only (`.side` is a sibling — never put `overflow-x:hidden` on `.shell` or axis-coupling recreates a content-sized CB on `.shell`).
- No `overflow:hidden` nav-open lock
- Keep flex short-page fill + unified foot-gap/safe-bottom + `right`-based drawer

## After update

Hard refresh + Clear Website Data. SW: `pgclock-shell-v23`. Restore: `v8.5.31`.

**Real iPhone still required for final confirmation** — CI uses Chromium + forced body-CB stand-in that reproduces short≠long; live CSS asserts body is not a scrollport.
