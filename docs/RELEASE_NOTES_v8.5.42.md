# v8.5.42 — the bottom bar never gets its colour from an overlay again

The reported symptom, in the user's words: the page loads full-height with a
transparent bottom, opening the drawer turns the strip under Safari solid (fine),
but **closing the drawer never brings the first state back** — the solid bar
stays and the content looks short.

## Root cause

Since iOS 26 / Safari 26 ("Liquid Glass") Safari no longer reads `theme-color`.
It colours its **own** status bar and bottom tab bar by sampling the page:

* it looks for `position: fixed` / `position: sticky` boxes that touch a
  viewport edge (within ~4 px of the top, ~3 px of the bottom, ≥ 80 % of the
  viewport width, ≥ 3 px tall),
* it reads that box's own `background-color` / `backdrop-filter`,
* `position: absolute` children and pseudo-elements are ignored,
* with no candidate it falls back to the `html` / `body` background,
* **and it does not re-sample when the sampled box goes away.**

The drawer backdrop was exactly the shape Safari samples:

```css
.side-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.55); }
```

So the sequence was:

| state | bottom bar |
| --- | --- |
| first paint | no candidate → root background `#09090b` → reads as page ("transparent") |
| drawer open | candidate found → dim `rgba(0,0,0,.55)` over the page → **solid** |
| drawer closed | backdrop is `display: none` again, but Safari keeps the last sampled colour → **still solid** |

Measured on the user's screenshots (iPhone 16 Pro Max, 1320 × 2868 device px,
DPR 3 → 440 × 956 CSS px): the strip below y = 856.7 CSS px is a flat `#040406`
across the full width — which is exactly `rgba(0, 0, 0, 0.55)` composited over
the `#09090b` page background (9 × 0.45 ≈ 4). The bar was painting the backdrop's
dim, not page pixels. Nothing about the page geometry was wrong: an opaque bar
covering the bottom ~99 CSS px is what made the content look shortened.

## Fix

One invariant, documented as invariant **E** next to the other mobile
invariants in `panel.css`: *a full-viewport fixed overlay keeps its own box
transparent and paints on an absolute child.* The bottom bar then always falls
back to the root background and is identical in every overlay state, so there is
no overlay colour left for Safari to freeze on.

| element | before | after |
| --- | --- | --- |
| `.side-backdrop` | `background: rgba(0, 0, 0, 0.55)` on the fixed box | `background: transparent`; dim on `.side-backdrop::before` (`position: absolute; inset: 0`) |
| `.panel-nav-clock` | `color-mix(...)` matte on the fixed box | matte on `.panel-nav-clock::before` (`z-index: -1`, so it stays behind the dial) |
| `.ui-modal` | already correct — `.ui-modal-backdrop` is an absolute child | unchanged |
| `.side` | `min(300px, 86vw)` → up to 86 % of the viewport width, i.e. a tint candidate on narrow phones | `--drawer-w: min(300px, 78vw)`, used for both `width` and the closed `right` offset |

The dim is now a token (`--side-dim`), so the light theme retints it instead of
repainting the fixed box; the old `html[data-theme="light"] .side-backdrop.show`
override is gone. Nothing about the drawer geometry, the scroll model or the
`svh` fill height changed — v8.5.40's invariants A–D are untouched.

## Removed

The `?vp=1` viewport diagnostic shipped in v8.5.41 (`_viewport_probe.html`,
`tests/test_viewport_probe.py`, its `base.html` include and the probe harness's
query-string branch). It existed to identify this root cause; keeping it would
leave dead code behind.

## Verification

`tests/overlay_root_scroll_probe.py` (WebKit + Chromium, real `base.html` +
`panel.css` + `panel.js`) now replays Safari's sampling rules in the browser. In
every measured state it asserts that:

* no fixed box with its own background/`backdrop-filter` covers ≥ 80 % of the
  viewport width at the bottom edge — in **any** drawer state,
* the only status-bar tint source on mobile is the opaque `.topbar`,
* the root background is not transparent (it is the fallback Safari samples),
* the drawer dim still paints while the drawer is open,
* and a screenshot taken after the drawer closes matches the pre-open
  screenshot (worst per-channel delta ≤ 2, i.e. text re-rasterisation only).

Result: `240 states, 2 engines` — 11 viewports (phone/tablet/desktop, portrait
and landscape, with and without notch insets, plus a Safari-toolbar-expanded
variant) × 3 page lengths × 4 states, all passing.

`tests/test_safari26_chrome_tint.py` locks the invariant in the stylesheet
itself so a future dim on a fixed overlay fails in CI rather than on a phone.

SW: `pgclock-shell-v32`. Restore: `v8.5.34`.
