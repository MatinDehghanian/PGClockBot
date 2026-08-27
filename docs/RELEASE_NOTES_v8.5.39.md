# v8.5.39 — Dark canvas + one footer height (light & dark)

## Root cause of the white bar (dark theme, Safari)

Screenshots showed a **white** strip under short pages and under the open
sidebar, ending at the same Y as the drawer/backdrop. Nothing in the dark panel
painted `#fff` — WebKit’s **default light canvas** showed below `100svh` because:

- CSS never set `color-scheme: dark` (only light set `color-scheme: light`)
- `meta color-scheme` was the ambiguous `dark light`
- `panel.js` skipped `theme-color` updates on `ios-safari` (stale Liquid Glass leftover)

## Fix

1. `:root` / `html[data-theme=dark]` → `color-scheme: dark`; light stays `light`
2. Boot + theme toggle sync `meta color-scheme` and solid `theme-color` (`#09090b` / `#fafafa`)
3. Explicit `background-color` + `background` on `html` / `body` / `.shell` / `.main` / `.side`
4. Mobile footers share one **fixed** box:  
   `min-height` = `max-height` = `calc(var(--footer-bar-h) + var(--bottom-inset))`  
   on both `.site-footer` and `.side .side-foot` (single-line content, no wrap growth)
5. Drawer stays `top` + `bottom: 0` (full layout height); backdrop full-bleed `rgba(0,0,0,0.55)`
6. Keep instant sidebar close; no transparent glass / `--vvh` / vh ping-pong

SW: `pgclock-shell-v30`. Restore: `v8.5.34`.
