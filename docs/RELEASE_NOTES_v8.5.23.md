# v8.5.23 — v8.2.8 geometry without page loading

## Problem

v8.5.17–v8.5.22 all used the same **100lvh + document lock + bottom:0** mobile layout.
The user confirmed **v8.2.8 worked** but later versions did not.

No agent had tried the combination of:
- **v8.2.8 layout geometry** (100dvh shell, calc sidebar height)
- **without** page-loading veil/skeleton/armVeil (removed in v8.5.22)

## Changes

### Mobile CSS (`panel.css`)

- Restore v8.2.8 shell: `height: 100dvh; max-height: 100dvh`
- Restore v8.2.8 sidebar: `height: calc(100dvh - topbar - safe-top)` (no `bottom: 0`)
- Remove `html:has(.shell) { overflow: hidden }` document lock
- Remove `html.ios-safari` transparent shell / visibility hacks
- Keep `--foot-gap` footer padding from v8.5.20
- Keep no page-loading system from v8.5.22

### Service Worker

- Bump cache to `pgclock-shell-v13`

## Restore

```bash
git checkout v8.5.22
```
