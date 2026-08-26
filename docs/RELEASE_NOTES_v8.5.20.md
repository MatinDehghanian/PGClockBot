# PGClockBot v8.5.20 — Release Notes

**Tag:** `v8.5.20`
**App version:** `8.5.20`
**Restore point:** tag `v8.5.19`

## Root cause (confirmed)

v8.5.16–v8.5.19 stacked **conflicting viewport hacks** on top of the working v8.2.8/v8.2.12 mobile shell:

| Hack | Symptom |
|------|---------|
| `--safari-overlay: max(0, 100lvh − 100svh)` on `.side` **and** extra `padding-bottom` | Empty solid strip under open sidebar (Safari screenshot) |
| `html/body { height: 100lvh; overflow: hidden }` document lock | Content pushed under fixed topbar (Chrome screenshot) |
| `.side:not(.open) { height: 0 !important }` on **all** mobile browsers | Broken first paint / stray unstyled nav links on black screen |
| Replacing `100dvh` shell with `100lvh` + `max-height: none` | Footer drift, black bars, layout unlike confirmed-good v8.2.8 |

Reverting only footer CSS to v8.2.8 could not fix this — the broken rules lived in the **mobile `@media` block**, SW stale cache, and later versions reintroduced the hacks.

## Fix

1. **Restore v8.2.12 mobile layout verbatim**
   - `.shell`: `height/max-height: 100dvh`, `padding-top` for fixed topbar
   - `.side`: `height: calc(100dvh − topbar − safe-top)` — full drawer height
   - `.main`: sole inner scroller, sticky footer unchanged
   - No `--safari-overlay`, no document lock, no `height:0` drawer collapse

2. **Safari 26 sampling guard only** (from v8.5.15, no dimension changes)
   - `html.ios-safari .shell { background: transparent }`
   - `html.ios-safari .main { background: var(--background) }`
   - `html.ios-safari .side:not(.open) { visibility: hidden }`

3. **Loading safety** — `_panel_widgets_defer.html` 12s veil timeout so dashboard never stays blank forever

4. **Service worker** — bump to `pgclock-shell-v10`, keep network-first for versioned `panel.css` / `panel.js`

## Deploy

1. Update to **8.5.20**
2. **Once per device:** Safari → clear website data for the panel domain **or** unregister the old service worker (Settings → Advanced → Website Data). Without this, cached v8.5.19 CSS may persist.
3. Hard-refresh and verify on iPhone Safari + Chrome.
