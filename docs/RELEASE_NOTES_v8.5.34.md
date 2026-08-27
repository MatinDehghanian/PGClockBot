# v8.5.34 — Final geometry from real iPhone screenshot

## What the screenshot proved (v8.5.33)

1. Dead black band under **both** the page and the open sidebar  
2. Main footer separator **higher** than sidebar footer separator  
3. Therefore fill height < visible viewport, and the two footer inset paths were not the same edge

## Root fixes

| Issue | Cause | Fix |
|--|--|--|
| Bottom gap | Empty `safe-bottom` pad on `.shell` looked like a gap; `min-height:0` blocked fill; `-webkit-fill-available` after `100svh` collapsed to stretch in Chromium | `padding-bottom:0` on `.shell`; html/body/shell `min-height` chain ending with **`100svh` last** |
| Footer misalignment | `.main {padding-bottom:inset}` vs `.side-foot {padding-bottom:inset}` with unequal content-box heights → separators at different Y | **One path:** both `.site-footer` and `.side-foot` own `padding-bottom:var(--bottom-inset)` + shared `--footer-bar-h`; `.main` has **no** bottom inset |
| Nav clock never shown | CSS delay frozen by WebKit on MPA nav; setTimeout lost the race | Arm shows clock **immediately** |
| CSS/fonts sometimes missing | SW network fail + no cache for new `?v=` URL | Fallback match by pathname ignoring query (SW v25) |

## Keep

- Document/viewport scroll; `.main` not a vertical scroller  
- No `--vvh` / visualViewport JS / fixed footer  
- Fixed sidebar `bottom: 0` without transform  

SW: `pgclock-shell-v25`. Restore: `v8.5.33`.
