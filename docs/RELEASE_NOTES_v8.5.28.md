# v8.5.28 — Final mobile bottom gap fix (document scroll, no viewport hacks)

## Root cause (measured)

Nested mobile scroll model + fixed viewport shell:
- `.shell { height: 100dvh; overflow: hidden }`
- `.main { overflow-y: auto }`

On iOS first paint, `100dvh` can exceed the visual viewport (URL bar expanded). First scroll triggers viewport reconciliation → shell height jumps → artificial bottom gap shrinks.

## Fix — one scroll model

| Layer | Mobile |
|-------|--------|
| Scroll owner | **document** (`html/body overflow-y: auto`) |
| `.main` | `overflow: visible` (not a scroller) |
| `.shell` | `flex: 1 0 auto; height: auto; overflow: visible` (no `100dvh`) |
| Short-page fill | `body { display:flex; min-height:100% }` + shell `flex:1` |
| Safe area | `.shell` padding-bottom only |
| Footer air | `.main` `--foot-gap` only |

No `--vvh`, visualViewport JS, `--safari-overlay`, or vh/dvh/svh/lvh viewport sync hacks on mobile shell.

## Tests

`tests/mobile_scroll_journey_probe.py` — short + long page:
1. first load (URL bar expanded proxy)
2. small scroll
3. scroll to bottom
4. scroll back to top
5. sidebar open/closed

Asserts: single scroll owner, invariant footer/shell gaps, no artificial blank below footer.

**Note:** Verified in Playwright/mobile viewport only — not on physical iPhone.

## After update

Hard refresh + Clear Website Data. SW cache: `pgclock-shell-v18`. Restore: `v8.5.27`.
