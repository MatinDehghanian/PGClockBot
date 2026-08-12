# PGClockBot v5.1.9 — Release Notes

**Tag:** `v5.1.9`  
**App version:** `5.1.9`

---

## Changes

- Colors tab: white option label is now **سفید** (removed «پیش‌فرض»).
- Tab titles: **رنگبندی دکمه‌ها** (was رنگبندی), **هویت ربات** (was ظاهر ربات).
- Colors catalog: reseller plan label **PAYG** (was Pay As You Go).
- Dead-code cleanup around button styles: single `STYLE_OPTIONS` source for the UI, dropped unused aliases / `VALID_STYLES` / `keys_for_reseller_colors`, and an unreachable `rev_no` branch in reply keyboard styling.

## Deploy

1. Backup as usual.
2. Deploy `main` / tag `v5.1.9`.
3. Hard-refresh the panel.
