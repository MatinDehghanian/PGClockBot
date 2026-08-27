# v8.5.36 — Instant sidebar close + backdrop parity (no vh ping-pong)

## Keep (v8.5.34)

Footer inset unity, immediate nav clock, document scroll, no `--vvh`, no `fill-available` after `100svh`.

## Explicitly NOT in this release

Another `100svh` / `100dvh` / `100lvh` geometry swap for the short-page gap.
That cycle moved the bug for dozens of releases and is rejected here.

## Fixes

1. **Browser backdrop too matte vs PWA** — removed ios-safari-only blur; same dim as PWA.
2. **PWA: sidebar stayed open during loading** — close in capture **before** nav clock, with transition disabled for that close.
3. **ios-safari glass sampling** — transparent shell + closed drawer `height: 0` (no opaque fixed paint at the bottom edge when closed).

Short-page / open-drawer gap remaining on device → next step is a minimal fixed-drawer repro on the same iPhone, not another viewport unit.

SW: `pgclock-shell-v27`. Restore: `v8.5.34`.
