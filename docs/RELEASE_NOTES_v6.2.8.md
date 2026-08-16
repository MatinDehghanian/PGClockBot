# PGClockBot v6.2.8 — Release Notes

**Tag:** `v6.2.8`  
**App version:** `6.2.8`

---

## Plan parity (web + API + bot)

### PAYG

- Quick-buy «حجم/کاربر اضافه» is **fixed subscription only**.
- Web create/edit hides the switch + unit prices for PAYG; API forces `allow_buy_extra=False` and zero unit prices.
- Bot admin toggle/edit and reseller menu follow the same rule; capacity purchase rejects PAYG.

### Addon packs (حجم / کاربر)

- No groups, PG role, web/bot permissions, or service naming — capacity + price only.
- Bot admin wizard and detail keyboard match the web modal; overview lists addon packs.

## Deploy

In-panel update to `6.2.8` (no new migration).
