# PGClockBot v5.2.1 — Release Notes

**Tag:** `v5.2.1`  
**App version:** `5.2.1`

---

## Changes

- Removed **order staff notes** (UI, API route, `Order.staff_note`). User staff notes remain.
- Receipt photos open in a **rounded `ui-modal`** (close to return to the panel); thumb + image use rounded corners.
- Behavior stats use the same **`stat-ico`** language as other home panels.
- Chat live preview applies saved **button colors on every preview tab** (fixed empty-string → default bug).
- Colors catalog expanded (~115 buttons) so reply hubs (admin / reseller / PG / loyalty / backup / …) are colorable; trial plan kind wired.
- **Security:** receipt proxy never cross-uses platform↔reseller bot tokens; platform payment list excludes reseller-tenant topups; path/type/size hardened; `Cache-Control: private, no-store`.

## Deploy

1. Backup as usual.
2. Deploy `main` / tag `v5.2.1`.
3. Hard-refresh the panel.
