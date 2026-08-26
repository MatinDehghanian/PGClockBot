# PGClockBot v8.5.19 — Release Notes

**Tag:** `v8.5.19`
**App version:** `8.5.19`
**Restore point:** tag `v8.5.18`

## Context

v8.5.18 made the **document** the scroller and sized `--safari-overlay` with **`100dvh`**. That matches neither PWA nor a stable in-browser chrome:

1. **Sidebar solid bar** — opening the drawer sets `nav-open` overflow lock and paints a dark `position:fixed` backdrop to `bottom: 0` (layout viewport). Safari 26 samples that edge → solid slab. PWA has no floating chrome, so it never showed.
2. **Jitter at the bottom** — scrolling the document collapses the URL bar while `100dvh` (and thus padding) changes on every frame.

## Fixes

1. **PWA-like scroll model in the browser**
   - `html/body/.shell`: `height: 100lvh; overflow: hidden` (document does not scroll; URL bar does not dance).
   - `.main` is the only scroller (`overflow-y: auto`).
   - `.main::after { flex: 0 0 1px }` so short pages still rubber-band without touching the document.

2. **Stable overlay inset**
   - `--safari-overlay: max(0px, 100lvh - 100svh)` — **not** `100dvh`. Constant while scrolling. PWA: `lvh ≈ svh` → `0`.

3. **Open drawer / backdrop**
   - `.side` and `.side-backdrop` `bottom: var(--safari-overlay)` so opaque paint stops above overlay chrome (closed drawer still `height: 0`).

4. Kept users table tags, boxed service menu, inbox vertical centering.

5. Service worker cache **`pgclock-shell-v9`**.

## Deploy

In-panel update to **8.5.19**. Hard-refresh Safari once so `panel.css?v=8.5.19` and SW v9 load.
