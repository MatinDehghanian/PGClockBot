# PGClockBot v8.5.5 — Release Notes

**Tag:** `v8.5.5`
**App version:** `8.5.5`
**Restore point:** tag `v8.5.4`

## Fixes

1. **Edit modal not opening**
   - Root: `{% set manage = ... %}` (and `flt`/`c`/`ops`/`bulk_count`) were declared inside `{% block content %}` in `users.html`. Jinja2 `{% set %}` inside a block is local to that block, so `manage` was undefined (falsy) in the separate `{% block page_scripts %}`, silently skipping the whole `{% if manage %}` script that wires up the edit-modal loader.
   - Fix: moved the declarations to template top-level so both blocks share them.

2. **Users table unreadable on small screens**
   - Root: once `.col-hide-sm` collapses the table to name/status/actions under 1100px, auto table layout still sized `col-name` to fit the longest *unwrapped* name + role/risk badges, regularly exceeding the viewport and silently pushing the row-actions (kebab) column off-screen with no scroll hint. The `وضعیت` header also got ellipsis-truncated.
   - Fix: `.users-ops-table` uses `table-layout: fixed` under the same breakpoint with explicit widths for the status/actions columns, so `col-name` reliably gets the remaining space. Verified with no horizontal table scroll down to 280px wide viewports.

3. **Black bar at bottom of page**
   - Root: an earlier revision (v8.5.3) changed `.main-body` to `flex: 0 0 auto` and `.site-footer`'s `margin-top` to `0`, which conflicted with the pre-existing sticky-footer contract and left a dark gap below the footer on short pages that only cleared after scroll / `100dvh` recalculation on mobile.
   - Fix: restored the classic sticky-footer pattern (`.main-body { flex: 1 0 auto }`, `.site-footer { margin-top: auto }`, desktop + `<=900px`) and added a JS nudge (`panel.js`) dispatching a synthetic `resize` on load/`pageshow` so mobile browsers that settle `100dvh` late recompute the layout before first paint.

## Deploy

In-panel update to `8.5.5` (no new migration). Hard-refresh after update.
