# PGClockBot v8.5.3 — Release Notes

**Tag:** `v8.5.3`  
**App version:** `8.5.3`  
**Restore point:** tag `v8.5.2`

## Fixes

1. **User edit modal stuck on loading**
   - `panel:modal-load` fires in the same click as `openModal`
   - PG snapshot wait capped at 3s; fragment errors return HTML (not redirects)
   - Client abort after 12s with visible error

2. **Users table (mobile)**
   - Tags under name: wrap with max ~2 per row (`.cell-name-tags`)
   - Wider service column; volume + expiry as real columns (not meta under service)

3. **Phantom box below content on first load**
   - Root cause: `.main-body { flex: 1 0 auto }` + `.site-footer { margin-top: auto }` filled the viewport with an empty slab
   - Fix: content-sized main-body (`flex: 0 0 auto`) and `margin-top: 0` on site-footer

4. **Section tabs** — first active tab pins to start (no leading black gutter)

## Deploy

In-panel update to `8.5.3` (no new migration). Hard-refresh after update.
