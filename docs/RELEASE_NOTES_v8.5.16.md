# PGClockBot v8.5.16 — Release Notes

**Tag:** `v8.5.16`
**App version:** `8.5.16`
**Restore point:** tag `v8.5.15`

## Context

The bottom “black bar” on iPhone survived v8.5.4–v8.5.15. Those patches treated it as Safari chrome tint, `visualViewport` timing, `--vvh`, or a sticky-footer bug. Pixel measurements of the user’s screenshots show the strip is **in-page** `background: #09090b` (`--background`), ~62pt below the shell/sidebar, with the footer sitting above that leftover.

## Root cause

On iOS 26 the **layout viewport** (what `%` / `100vh` / `100lvh` fill) is the large viewport. `100dvh` is the **small** dynamic viewport (above the overlay tab bar / home-indicator chrome).

The mobile shell was:

```css
.shell { height: 100dvh; max-height: 100dvh; }
.side  { height: calc(100dvh - topbar - safe-top); }
.main  { max-height: 100dvh; } /* inherited from desktop, never overridden */
```

So the app frame stopped short of the real page bottom. `html, body` still filled the large box, painting `--background` in the gap — the black bar. The sidebar could not cover it (same `dvh` cap). Overscrolling `.main` sometimes chained to the document, so page content appeared to slide over the gap; the fixed drawer never did.

Safari 26 sampling (`transparent` shell, `theme-color`) was a separate, real quirk, but it was **not** this bar. Making `.shell` transparent made the gap more obvious.

## Fixes

1. Mobile shell fills the **layout** viewport: `height/min-height: 100lvh` (`100vh` fallback), `max-height: none` (overrides desktop `max-height: 100dvh`).
2. `html:has(.shell)` / `body` lock to `100lvh` + `overflow: hidden` so leftover document space cannot show through.
3. Mobile `.main` unsets desktop `max-height: 100dvh`.
4. Mobile `.side` uses `top` + `bottom: 0` (no `dvh` height cap) so the open drawer reaches the screen edge.
5. Closed iOS Safari drawer: `visibility: hidden` **and** `bottom: auto; height: 0` so it is not sampled at the viewport edge.
6. `overscroll-behavior-y: contain` on `.main` and `.side` — no document-scroll leak onto the gap.
7. Service worker cache bumped to `pgclock-shell-v6`.

## Deploy

In-panel update to **8.5.16**. Hard-refresh Safari (or clear site data once) so `panel.css?v=8.5.16` and SW v6 replace any cached v8.5.15 assets.
