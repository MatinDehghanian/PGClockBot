# Release notes — v6.2.0

## Mini App — role shells (panel look)

- Role-aware Mini App shells: **user** / **reseller** / **admin** (same HTTPS URL; persona from Telegram `initData`)
- Visual language aligned with the web panel (dark shadcn tokens, brand orange, Vazirmatn, bottom nav)
- Deep links: `/miniapp/#ops`, `#services`, `#shop`, …
- Admin «نمایندگان» hub + reseller home offer Mini App shortcuts
- No Nginx required — existing panel SSL + `PUBLIC_BASE_URL` is enough
- Telegram **Open** menu button (`MenuButtonWebApp`) auto-syncs when Mini App is enabled
- Restore point before this work: branch `cursor/restore-before-role-miniapp-c615` / tag `restore/pre-role-miniapp-v6.1.18`
