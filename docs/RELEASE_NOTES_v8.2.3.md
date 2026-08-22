# PGClockBot v8.2.3 — Release Notes

**Tag:** `v8.2.3`  
**App version:** `8.2.3`  
**Restore point:** tag `restore/pre-node-select-modal-chrome-v8.2.2` (@ `v8.2.2`)

## What changed

1. **Node CPU/RAM bars match host gauge circles**
   - Same tone tokens (`--ok-fg` / `--warn-fg` / `--caution-fg` / `--destructive-fg` / `--muted-fg`)
   - Full opacity (no washed translucent fill)
   - Track mix aligned with gauge track (18%)

2. **No sharp focus/hover corners on selects & controls**
   - Focus ring uses `box-shadow` (follows radius) instead of rectangular `outline` on Android/WebKit
   - Select toggle / menu items / tone pills keep rounded radius on `:hover` `:focus` `:active` `:open`

3. **Modal scrollbars stay inside the rounded panel**
   - Panel `overflow: hidden` clips to `border-radius`
   - Inner `.ui-modal-scroll` (JS) owns scrolling

## What this does *not* change

- No migrations, no auth/ACL changes

## Update

In-panel update to `8.2.3` (no new migration). Hard-refresh the panel after update.
