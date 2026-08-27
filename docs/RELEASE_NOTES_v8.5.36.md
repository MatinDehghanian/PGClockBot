# v8.5.36 — Short-page Safari fill + instant sidebar close

## Keep (v8.5.34)

Footer inset unity, immediate nav clock, document scroll, no `--vvh`, no `fill-available` after `100svh`.

## Fixes

1. **Short page / open sidebar too high (Safari browser)**  
   `html.ios-safari`: `min-height: 100lvh` on html/body/shell; open `.side` / backdrop `bottom: calc(100svh - 100lvh)` so they reach the large-viewport edge. Transparent shell keeps chrome glassable.

2. **Browser backdrop too matte vs PWA**  
   Removed ios-safari-only blur/frost overlay — same backdrop opacity as PWA.

3. **PWA: sidebar stayed open until after loading**  
   Close sidebar in capture phase **before** arming nav clock, with `transition: none` for that close.

SW: `pgclock-shell-v27`. Restore: `v8.5.34`.
