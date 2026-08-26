# v8.5.27 — iOS scroll-viewport root fix (document scroll)

## Root cause (measured)

**Symptom:** first load = large bottom gap; one scroll = gap shrinks (iPhone Safari/Chrome/PWA).

**Mechanism:**
- `.shell { height: 100dvh; overflow: hidden }` sized to **layout viewport**
- `.main { overflow-y: auto }` = nested scroll owner
- On iOS first paint, `100dvh` ≈ layout viewport (taller than **visual viewport** when URL bar is visible)
- First scroll triggers `dvh` recalculation → shell height shrinks → bottom gap jumps

Probe (`tests/mobile_ios_scroll_probe.py`) confirms:
- Nested model: gap changes after simulated dvh recalc
- Document scroll model: `shell_bottom_delta=0`, `footer_bottom_delta=0`, `gap_delta=0` after first scroll

## Fix — one scroll owner

| Before | After |
|--------|-------|
| `.main` scrolls | **document** scrolls |
| `.shell height: 100dvh` | `.shell min-height: 100svh; height: auto` |
| `.shell overflow: hidden` | `.shell overflow: visible` |
| `.main overflow-y: auto` | `.main overflow: visible` |

`100svh` used only for shell **min-height** (stable while URL bar animates — not a blind global vh swap).

## Removed

- Nested `.main` scroll on mobile
- Fixed `100dvh` shell height on mobile
- `body.nav-open .main { overflow: hidden }` (document lock via `body.nav-open` only)

## After update

Hard refresh + Clear Website Data. SW cache: `pgclock-shell-v17`. Restore: `v8.5.26`.
