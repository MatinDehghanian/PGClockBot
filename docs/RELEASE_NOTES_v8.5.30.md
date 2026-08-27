# v8.5.30 — Short-page footer fill + sidebar gap + nav clock

Keeps the v8.5.28 document-scroll architecture. No viewport-unit / `--vvh` hacks.

## 1) Short-page footer

**Cause (measured):** v8.5.29 set `main/footer flex:0` + `margin-top:0`, so short pages left `shell_to_layout ≈ 464px` empty below the footer.

**Fix:** Restore content-safe flex fill without vh units:
- `html { height:100% }` / `body { min-height:100%; display:flex }`
- `.shell` / `.main` → `flex: 1 0 auto`
- `.site-footer` → `margin-top: auto`
- Blank *below* footer stays `foot-gap + safe-bottom` only

## 2) Sidebar gap (Safari/PWA)

**Cause (measured):**
1. `body.nav-open { overflow:hidden }` shrinks iOS fixed containing block → gap under drawer/backdrop
2. `padding-bottom: safe-bottom` on `.side` looked like the drawer box was shortened

**Fix:**
- Lock scroll with `html:has(body.nav-open) { overflow:hidden }` — body overflow stays visible
- `.side { padding-bottom: 0; bottom: 0 }` — background paints to viewport bottom
- `.side .side-foot { padding-bottom: var(--safe-bottom) }` — inner safe-area only
- Removed closed-drawer `height:0` collapse

## 3) Navigation clock

Lightweight `#panel-nav-clock` (reuses `.panel-load-clock` mark):
- `position:fixed; pointer-events:none; background:transparent`
- Arms on internal link click / form submit after 140ms (anti-flicker)
- Clears on `pageshow` / `pagehide`
- **Not** the old `page-load-veil` / skeleton

## After update

Hard refresh + Clear Website Data. SW: `pgclock-shell-v20`. Restore: `v8.5.29`.
