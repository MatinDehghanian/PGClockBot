# PGClockBot v7.0.3 — Release Notes

**Tag:** `v7.0.3`  
**App version:** `7.0.3`  
**Restore point:** branch `cursor/restore-before-ux-speed-pulse-5b2d` / tag `restore/pre-ux-speed-pulse-v7.0.2` (@ `6d23c9e`, v7.0.2)

---

## Speed

- Home first paint is a local-DB shell; Bot / PasarGuard / nodes hydrate via `GET /home/live`.
- Self-hosted Vazirmatn (Google Fonts removed from CSP).
- Gzip middleware; identity-keyed PG GET cache; 20s sidebar unread cache.
- Same-origin GET content-swap for `#panel-page`.
- Shop period stats: fewer SQL round-trips + previous-period deltas.

## Design

- Admin and reseller dashboards: pulse sentence, action queue, compared sales, wallet box.
- More modal inner padding and head divider.
- Empty-state CTA pattern; warmer login wash.
- Mini App: service-first home, checkout cards, themeParams, haptic, retry empty.
- Bot: role home status, delivery next-step, ticket queue copy, actionable PG errors.

## Deploy

In-panel update to `7.0.3` (no new migration). Hard-refresh the panel and Mini App after update.
