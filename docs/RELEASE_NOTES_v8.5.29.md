# v8.5.29 — Micro-fix: sidebar gap + short-page footer gap

## 1) Sidebar gap (Safari, open drawer)

**Measured:** `.side` and `.side-backdrop` both reached layout bottom (delta=0), but `.side` had `padding-bottom: calc(foot-gap + safe-bottom)` = 50px vs backdrop with no padding — visible empty strip below `side-foot` inside drawer, and safe-area stacked with shell's safe-bottom concept.

**Fix:** Mobile `.side` padding-bottom → `var(--safe-bottom)` only. Closed drawer: `height: 0; overflow: hidden` on `.side:not(.open)` so fixed off-screen drawer doesn't inflate scroll geometry.

## 2) Short-page footer gap

**Measured:** `content_to_footer: 488px` from `body { display:flex }` + `shell/main { flex:1 }` + `footer { margin-top:auto }` stretching empty space above footer. Shell forced to 844px viewport while content ~380px.

**Fix:** Remove mobile body flex stretch. `main { flex: 0 0 auto }`, `footer { margin-top: 0 }`, `html/body { min-height: 0; height: auto }` on shell pages. Footer stays in normal flow; below-footer spacing = foot-gap (16px) + shell safe-bottom (34px) only.

**Document-scroll architecture unchanged.**

## After update

Hard refresh + Clear Website Data. SW: `pgclock-shell-v19`. Restore: `v8.5.28`.
