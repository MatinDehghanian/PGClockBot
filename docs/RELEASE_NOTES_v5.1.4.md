# PGClockBot v5.1.4 — Release Notes

**Tag:** `v5.1.4`  
**App version:** `5.1.4`

---

## Changes

- **رنگبندی:** new bot-settings tab (`/settings?tab=colors`, also shop-settings) to pick Telegram button colors per button: blue (`primary`), green (`success`), red (`danger`), or white/default. Sensible defaults match the previous hardcoded mapping.
- **Front/back sync:** styles stored as `btn_style_*` settings; reply + inline keyboards (and one-tap renew / approval notifications) read the same keys; invalid values are normalized on save.
- **رفتار کاربر:** remaining user-facing «فانل خرید» copy (funnel page title, tracking toggle, nightly report) renamed to «رفتار کاربر».

## Notes

- Telegram button colors require a client that supports Bot API 9.4+; reopen the menu (`/start` or home) after changing colors so a fresh keyboard is sent.
- Purchase simulator remains a walkthrough inside the live settings preview — not a separate page and not real checkout.

## Deploy

1. Backup as usual.
2. Deploy `main` / tag `v5.1.4` (ensure `VERSION` reads `5.1.4`).
3. Restart panel/bot so settings defaults seed and keyboards pick up styles.
