# PGClockBot v5.2.8 — Release Notes

**Tag:** `v5.2.8`  
**App version:** `5.2.8`

---

## Why this release

Dashboard accordion for alerts cluttered `/home`. Tools hub was redundant after moving links to bot settings and gift codes to plans. This release makes **اعلان‌ها** a first-class sidebar page and removes leftover tools UI/routes.

Also includes the unfinished v5.2.7 UX work (backup health tag, copy-button fix, Telegram tickets from web panel).

## Inbox page

- New `/inbox` between dashboard and web-panel settings in the sidebar.
- Same `nav-dot` as پشتیبانی when there are alerts.
- Holds update banner, ticket alerts, maintenance/capacity/PAYG strips, and action center.
- Dashboard no longer embeds the accordion.

## Tools removed

- Deleted `tools.html`, `gift_codes.html`, `magic_links.html`, `_home_inbox.html`.
- Removed all `/tools*` routes.
- Gift codes: `POST /plans/gift-codes` (+ toggle).
- Shop bundle: `GET /settings/shop-export`, `POST /settings/shop-import`.

## Also in this train (from v5.2.7)

- Backup health: small tag next to latest backup (+ verify).
- Quick-link copy: idle label resets after «کپی شد».
- Magic links tab in bot settings; gift codes button on plans.
- Telegram user tickets controllable from `/tickets` (reply delivers to Telegram; tenant-scoped).

## Security

- Inbox context does not expose bot tokens/secrets.
- Shop export still skips `bot_token` and `webhook_secret`.
- Gift-code and bot-ticket routes keep tenant isolation.

## Deploy

Deploy `v5.2.8` (or in-panel update). Hard-refresh the panel. Confirm sidebar «اعلان‌ها», `/inbox`, gift modal on plans, and backup export/import under settings → backup. Old `/tools` bookmarks will 404 by design.
