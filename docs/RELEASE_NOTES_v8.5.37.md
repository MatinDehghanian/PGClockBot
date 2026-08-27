# v8.5.37 — Real fix: light-theme cascade + PWA/Safari drawer glass

## Why v8.5.36 failed on device

Screenshots were **light theme**. This rule appears *later* in `panel.css` than the
v8.5.36 ios-safari paint hacks:

```css
html[data-theme="light"] .side { background: #ffffff; }
```

Equal specificity → light theme won → the whole drawer stayed solid white through
the bottom inset. PWA never got the hack at all (`ios-safari` only).

## Fix

1. **Cascade:** iOS drawer glass rules now sit **after** the light-theme `.side`
   background, with `background: transparent !important` on `html.ios .side.open`.
2. **Both Safari and PWA** (`html.ios`): opaque card fill is a `::before` that ends
   at `bottom: var(--bottom-inset)` — the inset band is truly transparent.
3. **Backdrop parity:** one `rgba(0,0,0,0.55)` for all iOS — no Safari-only
   gradient/blur. Backdrop `right: min(300px, 86vw)` so it never dims the drawer
   gutter (the grey undershoot strip under the sidebar was that dim showing).

## Keep

v8.5.34 geometry, instant nav close, no `--vvh` / vh ping-pong.

SW: `pgclock-shell-v28`. Restore: `v8.5.34`.
