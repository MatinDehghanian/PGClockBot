# PGClockBot v5.1.5 — Release Notes

**Tag:** `v5.1.5`  
**App version:** `5.1.5`

---

## Changes

- **Removed** the purchase simulator from the Telegram live preview (button + JS walkthrough).
- **رنگبندی redesign:** each button is its own tile with a native `<select>` (سفید / آبی / سبز / قرمز); category cards kept; responsive grid **2 → 3 → 4** columns; uses panel tokens (`--background`, `--border`, `--card-pad`, `--section-gap`) for light/dark.
- **Backup tab:** shop settings export/import block moved to the **top** of `/settings?tab=backup`.

## Deploy

1. Backup as usual.
2. Deploy `main` / tag `v5.1.5` (ensure `VERSION` reads `5.1.5`).
3. Hard-refresh the panel so `panel.css` updates.
