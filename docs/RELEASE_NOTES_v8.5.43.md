# v8.5.43 — Safari bar restore, reliable first paint, nav clock on every page

Three mobile reports from the same session:

1. **Safari bottom bar** — page loads full with a transparent bottom; opening the
   drawer makes the strip solid (fine); closing the drawer left it solid and the
   content looked short.
2. **Intermittent broken load** — duplicate `MrClockBot` brands, theme chip and
   nav labels on a black void until refresh (screenshot 3).
3. **Nav clock missing** — especially when opening **Plans** from the drawer.

## Safari bottom bar

v8.5.42 already stopped overlays from tinting Safari 26's toolbars (dim on
`.side-backdrop::before`, drawer capped at `78vw`). That invariant stays. This
release does not put colour back on any full-bleed fixed box.

## Broken first paint (screenshot 3)

`color-scheme: dark` without `panel.css` paints a black canvas and leaves both
the mobile topbar brand and the desktop `.brand.desk-only` visible — exactly the
"refresh to fix" screenshot.

| change | why |
| --- | --- |
| `#panel-critical-boot` inline in `base.html` | hides `.desk-only` on mobile, pins a minimal shell + backgrounds before `panel.css` arrives |
| `rel=preload` for `panel.css` | starts the stylesheet sooner |
| SW `pgclock-shell-v33` | network-first panel assets now fall back to cache on **non-OK** responses too (not only network errors) |

`.side:not(.open) { visibility: visible }` in `panel.css` clears the critical-boot
`visibility: hidden` once the real stylesheet loads, so the off-screen `right`
slide remains the only closed-state mechanism.

## Nav clock on Plans (and every MPA target)

Closing the drawer in the same turn as a default `<a>` click slid the clicked
link off-screen and set `pointer-events: none` on `.side`. On WebKit that often
cancelled the default navigation paint path, so `#panel-nav-clock` never showed
for heavy targets like `/plans`.

Fix: `preventDefault` → close drawer → `arm()` → `requestAnimationFrame` →
`location.assign(href)`. One frame of clock paint is guaranteed before unload.
`panel.js` is no longer `defer`, so the handler is bound before the first tap.

Shell-first home/PG also arms the same clock while `/body` loads (still **not**
the deleted `#page-load-veil` / skeleton from v8.5.22).

## Verification

- `tests/test_nav_clock_paint_before_nav.py`
- `tests/test_safari26_chrome_tint.py` (unchanged invariants)
- `tests/test_panel_safe_speed.py` (clock on defer, no veil)
- `tests/test_restart_pwa_update.py` / `test_mobile_viewport_shell_fix.py` (SW v33)

SW: `pgclock-shell-v33`. Restore: `v8.5.34`.
