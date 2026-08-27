# v8.5.41 — viewport diagnostic (`?vp=1`)

No layout change. This release adds the instrument needed to close out the two
symptoms still reported on v8.5.40, both of which are **iOS-only** and neither of
which reproduces in WebKit or Chromium on CI.

## What is still wrong on v8.5.40

1. **Safari** — after the drawer closes, the bottom toolbar stays in its
   expanded, opaque state instead of collapsing back to the translucent pill.
2. **PWA, short pages** — an empty band at the bottom of the screen.

## What the v8.5.40 screenshots already prove

Pixel measurement of the two reported screenshots (iPhone 16 Pro Max,
1320 × 2868 device px, DPR 3 → 440 × 956 CSS px):

| measurement | value |
| --- | --- |
| `.topbar` height | 114 CSS px → `--safe-top` = **62** (matches this device) |
| PWA: bottom of `.side` and `.side-backdrop` | **894** CSS px |
| PWA: bottom of the screen | **956** CSS px |
| shortfall | **62** CSS px |
| colour of the band below | `#09090b` — the propagated `html` canvas background |

`.side` is `position: fixed; bottom: 0` and `.side-backdrop` is
`position: fixed; inset: 0`. Two fixed boxes cannot end above the viewport bottom
unless **their containing block — the initial containing block — is short**. And
the shortfall is not an arbitrary number: it is exactly
`env(safe-area-inset-top)`. The layout viewport is being shortened by the top
inset while still being positioned at the top of the screen, so the leftover band
lands at the bottom.

The band reads `#09090b` rather than black because the fix in v8.5.39 gave `html`
an explicit background, so the canvas paints it. That is why it now looks like an
empty gap rather than the black bar of earlier versions.

## Why a diagnostic instead of a fix

Several candidate mechanisms produce that exact signature (among them the legacy
`apple-mobile-web-app-status-bar-style: black-translucent` meta overlapping with
`viewport-fit=cover`, and iOS resolving `100svh` against a viewport that already
had the top inset removed). They call for **different** fixes, and choosing
between them from a screenshot is guessing — which is how this bug survived 40
releases. Two numbers from the device settle it:

- `D inner-de` (`innerHeight − documentElement.clientHeight`) non-zero → the
  layout viewport is genuinely short, and the drawer must stop using the ICB for
  its bottom edge.
- `D inner-svh` (`innerHeight − 100svh`) non-zero → `svh` is the wrong unit for
  the fill height on iOS.

## Using it

Append `?vp=1` to any panel URL on the device, e.g.
`https://dev.mrclock.website/?vp=1`. An overlay appears in the middle of the
screen reporting:

- `display-mode: standalone` vs browser, `navigator.standalone`
- `screen`, `devicePixelRatio`, `innerWidth/innerHeight`, `outerHeight`
- `documentElement.clientHeight` and `scrollHeight`, current and max scroll
- `visualViewport` height, `offsetTop`, `scale`
- resolved `100vh`, `100svh`, `100lvh`, `100dvh`
- resolved `env(safe-area-inset-*)` on all four sides
- the three deltas above
- `top > bottom` and the gap to `innerHeight` for `.topbar`, `.shell`, `.main`,
  `.site-footer`, `.side` and `.side-backdrop`

The numbers refresh live on scroll, resize, orientation change, visual-viewport
changes and whenever the drawer opens or closes, so one screenshot per state is
enough. `copy` puts the text on the clipboard; `hide` removes the overlay.

Screenshot it **four times**: Safari drawer-closed, Safari drawer-open, PWA
drawer-closed, PWA drawer-open.

## Safety

- Server-side gated on the query parameter, so it is not rendered, downloaded or
  parsed on a normal request.
- The `100vh`/`svh`/`lvh`/`dvh` measuring boxes are `position: fixed`, not
  `absolute`. As `absolute` they would have added roughly four viewports of
  `scrollHeight` and made a short page scrollable — falsifying the readings and
  changing the Safari toolbar behaviour under investigation. Verified in both
  engines: `scrollHeight` and `clientHeight` are identical with and without the
  probe, on short and long pages.
- The overlay is `pointer-events: none` except for its two buttons, and sits
  below the topbar, so it can never block the menu button or the drawer.
- Pinned by `tests/test_viewport_probe.py`.

SW: `pgclock-shell-v31` (unchanged — no static asset changed). Restore: `v8.5.34`.
