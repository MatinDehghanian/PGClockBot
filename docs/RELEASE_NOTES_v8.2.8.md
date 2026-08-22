# PGClockBot v8.2.8 — Release Notes

**Tag:** `v8.2.8`  
**App version:** `8.2.8`  
**Restore point:** tag `restore/pre-scroll-rubber-band-v8.2.7` (@ `v8.2.7`)

## What changed

1. **Natural scroll bounce (rubber-band) on page edges**
   - `overscroll-behavior-y: auto` on `.main` and `.side`
   - Mobile: page scroll lives on `.main` only (same as desktop), not `body` — fewer edge jitter / modal-lock fights

2. **Modal scroll at content edges**
   - `.ui-modal` uses `overscroll-behavior: contain` instead of `none`
   - JS wheel/touch guards skip `preventDefault` at interior scroll boundaries; backdrop / outside-modal bleed still blocked

3. **Mobile nav drawer**
   - `body.nav-open .main` overflow locked while the hamburger drawer is open

## What this does *not* change

- No migrations, no auth/ACL changes
- Modal background lock, horizontal modal tabs, kebab menus, and select porting unchanged

## Update

In-panel update to `8.2.8` (no new migration). Hard-refresh the panel after update.
