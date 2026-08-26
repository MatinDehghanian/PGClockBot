# v8.5.24 — measured height + shell-relative sidebar

## Why previous releases failed

v8.5.17–v8.5.23 all tuned **CSS viewport units** (`100lvh`, `100dvh`, `calc(...)`) on
`position: fixed` elements. On iOS Safari the layout viewport (`dvh`) is often **shorter**
than the visible screen — sidebar ends ~15–20% above the bottom (exactly what screenshots show).

## New approach (two changes, not another unit swap)

1. **Measure real height in JS** — `base.html` sets `--vvh` from `window.innerHeight` /
   `visualViewport.height` synchronously before CSS loads.

2. **Sidebar anchored to shell, not viewport** — mobile `.shell` is `position: relative;
   height: var(--vvh)`. Sidebar is `position: absolute; top: 0; bottom: 0` inside shell —
   no `calc(100dvh - topbar)`.

Also: revert `theme-color: transparent` for iOS (back to `#09090b` like v8.2.8).

## After update

Clear website data once, hard refresh. SW cache is `pgclock-shell-v14`.
