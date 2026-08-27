# v8.5.35 — Safari Liquid Glass (keep v8.5.34 geometry)

## Keep from v8.5.34 (confirmed on device)

- Footer separators aligned (`--bottom-inset` + `--footer-bar-h` on both footers)
- Nav clock shows immediately
- Document/viewport scroll (Safari chrome shrinks on scroll)
- No `--vvh` / nested `.main` scroll / transform drawer
- Do **not** put `-webkit-fill-available` after `100svh` (Chromium stretch collapse)

## Device leftovers after 8.5.34

1. Opening the sidebar in **Safari browser** made the strip under the page **solid** instead of native glass
2. Short pages looked like footer/sidebar sat too high (often the solid Safari-sampled slab)

## Fixes (`html.ios-safari` only — in-browser iOS, not PWA)

- Detect `ios` / `ios-safari` / `ios-standalone` in `<head>`
- `theme-color: transparent` on ios-safari
- Transparent html/body/shell; `.main` keeps `var(--background)`
- Closed drawer → `height: 0` (off-screen opaque fixed paint no longer tints toolbar)
- Open drawer keeps `bottom: 0` (footer align intact); last pixels faded/masked; frosted backdrop

SW: `pgclock-shell-v26`. Restore: `v8.5.34`.
