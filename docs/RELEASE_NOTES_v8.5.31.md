# v8.5.31 — Unified footer inset + iOS Safari sidebar + working nav clock

Keeps document-scroll. No `--vvh` / `100dvh` / nested `.main` scroll.

## A) Footer

One inset everywhere: **foot-gap + safe-bottom**.

- Main: `.main` padding-bottom = foot-gap; `.shell` padding-bottom = safe-bottom
- Sidebar: `.side` padding-bottom = 0 (drawer paints to `bottom:0`); `.side-foot` padding-bottom = `calc(foot-gap + safe-bottom)`
- Short pages: flex fill + `footer { margin-top:auto }` — empty space above footer, not below

## B) iOS Safari sidebar gap

**Cause:** `transform: translateX(...)` on `position:fixed` drawer. PWA (no URL bar) looked fine; Safari browser left a visible gap under the drawer.

**Fix:** Slide with `right` instead of `transform`. Backdrop shares the same `top`/`bottom:0` anchors.

## C) Loading clock

**Cause:** `setTimeout(140ms)` often never paints during full-page navigation (document teardown).

**Fix:** Remove `[hidden]` immediately on arm; CSS `animation-delay: 140ms` reveals opacity. Fast nav never shows the clock; slow nav does. New page HTML starts hidden; `pageshow`/`pagehide`/`popstate` disarm.

## After update

Hard refresh + Clear Website Data. SW: `pgclock-shell-v21`. Restore: `v8.5.30`.

**Note:** Real iPhone Safari not available in CI — verified in Playwright/Chromium with geometry probes.
