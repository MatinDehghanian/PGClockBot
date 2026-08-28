# v8.5.44 — real root cause: the drawer was still a scroll lock

## The bug that survived v8.5.40–43

Opening the sidebar expands Safari's bottom toolbar into a solid strip; closing
it never brings the first (full + translucent) state back. Content looks short.

v8.5.40 removed `overflow:hidden` / `touch-action:none` from `html`/`body`, then
**moved the same lock onto the drawer**:

```css
.side-backdrop { touch-action: none; }          /* full-viewport */
body.nav-open .topbar { touch-action: none; }   /* chrome above it */
```

CSS properties on the root looked "unlocked". Gestures were not: a
full-bleed `touch-action: none` overlay is a functional scroll lock. iOS Safari
expands its bottom toolbar when the page cannot scroll, and only retracts it on
a real scroll. After close, `scrollY` is usually `0`, so the solid bar stays.

v8.5.42–43 attacked a parallel theory (chrome tint from `background` on fixed
boxes). CI probes can assert that sampler; they cannot assert the mobile Safari
toolbar. The device kept failing.

## Fix — one rule, no new layer

**The open drawer must not make the document unscrollable by gesture.**

| before | after |
| --- | --- |
| `.side-backdrop { touch-action: none }` | removed — dim + tap-to-close only |
| `body.nav-open .topbar { touch-action: none }` | removed |
| pan on dim blocked | pan on dim may scroll the page (keeps Safari honest) |
| tap on dim closes | unchanged |

Tint hygiene from v8.5.42 (dim on `::before`) stays — it is cheap and still
correct — but it is no longer treated as the cause of the stuck bar.

## Hamburger during scroll

`#menu-toggle` listened only to `click`. On a `position: fixed` topbar over
document scroll, iOS suppresses that click until momentum settles. Fix:
`pointerup` (touch/pen) + `touch-action: manipulation`, with `click` for mouse.

## Cleanup (no parallel models)

- Shrink `#panel-critical-boot` to canvas colour + `.desk-only` hide only — the
  8.5.43 mini shell / `visibility:hidden` drawer fought `panel.css`
- Drop the `.side:not(.open) { visibility: visible }` undo that existed only
  for that fight
- Rewrite the self-contradictory probe that required "root unlocked" **and**
  "pan on backdrop must not scroll"

## Verification

- `tests/overlay_root_scroll_probe.py` — drawer open: backdrop `touch-action != none`,
  pan on dim scrolls, tap still closes, tint invariants unchanged
- `tests/test_scroll_rubber_band_fix.py`
- `tests/test_menu_toggle_tap.py`
- `tests/test_safari26_chrome_tint.py`

SW: `pgclock-shell-v34`. Restore: `v8.5.34`.
