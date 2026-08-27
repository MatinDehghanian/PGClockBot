# v8.5.36 — Liquid Glass paint band + instant sidebar close

## Keep (v8.5.34)

Footer inset unity, immediate nav clock, document scroll.
`min-height` chain ends with `100svh`. No `--vvh` / `visualViewport` sizing.
No `100svh` / `100dvh` / `100lvh` ping-pong.

## New approach (not the old cycles)

The leftover “footer too high / solid band under sidebar” on iOS Safari was
**not** fixed by another viewport-height guess. Those cycles failed for many
releases (`vh` swaps, measured `--vvh`, 3px fade + heavy blur).

**Root cause:** Safari 26 samples opaque paint near the bottom of the layout
viewport and tints browser chrome solid. Geometry stayed correct; the band was
sampled chrome.

**Fix (`html.ios-safari` only):** keep `bottom:0` / `100svh` geometry. Stop
opaque fill on `.main` and open `.side` above `--safe-bottom` (full home-
indicator band). Collapse closed drawer to `height:0`. Backdrop uses the same
dim as PWA, no `backdrop-filter`, and clears paint through `--safe-bottom`
while the box stays `bottom:0`.

## Also in this release

1. Instant sidebar close before nav clock (Safari and PWA)
2. PWA-matching backdrop dim (no extra browser blur)

SW: `pgclock-shell-v27`. Restore: `v8.5.34`.
