# v8.5.33 — Body fixed-CB + first-paint svh fill + WebKit-safe nav clock

Rolls back failed v8.5.32. Keeps document/viewport scroll (no nested `.main`).

## A) Sidebar short≠long (primary clue)

**Cause:** `body { overflow-y:auto }` → content-sized fixed CB; `.side` under body/shell.  
**Fix:** html+body+shell overflow visible; viewport scrolls; `.main { overflow-x: clip }` only.

## B) First-paint gap (tablet/Safari) — clears after scroll

**Cause:** `html { height:100% }` + `body { min-height:100% }` fill the **layout** ICB (`innerHeight`). With chrome, `visualViewport < innerHeight` → footer below visible fold (content looks pushed up). First scroll hides chrome → vv grows → gap gone **without CSS box change**.  
**Fix:** `min-height: 100svh` (small viewport) for html/body fill — one stable unit, not `100dvh` shell + nested scroll.

## C) Nav clock missing on slow pages

**Cause:** CSS `animation-delay` reveal. WebKit **freezes CSS animations** when MPA navigation starts; clock stays `opacity:0` until unload. `setTimeout` **does** fire (proven).  
**Fix:** `setTimeout(140)` anti-flicker, then show with immediate opacity; light matte background (not the deleted veil system).

## After update

Hard refresh + Clear Website Data. SW: `pgclock-shell-v24`. Restore: `v8.5.31`.

Confirm on device: short page first paint (no bottom gap), sidebar open short+long, slow nav shows clock+matte.
