# PGClockBot v7.0.5 — Release Notes

**Tag:** `v7.0.5`  
**App version:** `7.0.5`  
**Restore point:** branch `cursor/restore-before-chrome-polish-5b2d` / tag `restore/pre-chrome-polish-v7.0.4` (@ `43683e8`, v7.0.4)

---

## Design

- Bot (orange) and PasarGuard (blue) sidebar sections, home portals, and page-title icons: neutral fills with soft gradient borders.
- Page and modal titles: light accent line and slightly stronger weight.
- More modal inner padding.

## Speed (safe only)

- Self-hosted Vazirmatn; Google Fonts removed from CSP.
- Gzip middleware; identity-keyed PG GET cache; 20s sidebar unread cache.
- Intentionally **not** included: content-swap nav (wrong sidebar active) and the pulse home rewrite (`pulse.items` 500).

## Deploy

In-panel update to `7.0.5` (no new migration). Hard-refresh the panel after update.
