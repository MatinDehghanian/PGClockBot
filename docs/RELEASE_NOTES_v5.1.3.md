# PGClockBot v5.1.3 — Release Notes

**Tag:** `v5.1.3`  
**App version:** `5.1.3`

---

## Changes

- **رفتار کاربر:** purchase-funnel stats moved to Finance as the first tab (`/finance?tab=behavior`); removed from dashboard and tools.
- **Settings export/import:** UI moved under web-panel Backup (`/settings?tab=backup`); `/tools?tab=export` redirects there.
- **Dashboard shortcuts:** removed bot-settings shortcut.
- **PasarGuard open button:** same `btn-sm btn-ghost` sizing as «نمای کلی»; no mobile full-stretch.
- **Telegram button colors:** reply keyboard + more inline actions use Bot API `style` (primary/success/danger). Requires a Telegram client that supports Bot API 9.4+; reopen the menu (`/start` or home) after update so a fresh keyboard is sent.
