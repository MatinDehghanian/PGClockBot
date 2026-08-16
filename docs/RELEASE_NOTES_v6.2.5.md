# PGClockBot v6.2.5 — Release Notes

**Tag:** `v6.2.5`  
**App version:** `6.2.5`

---

## Features

### Time-limited PG admin subscription (reseller + pg_staff)

- Shared clock keyed by PasarGuard username (`pg_admin_subscriptions`).
- On expiry: web login off, PG admin disabled, owned users cut (IDs stored).
- On renew: automatic restore + period extend from `max(now, expires_at)`.
- PAYG plans are not time-gated.
- Scheduler tick every 5 minutes; owner can renew staff from `/pg/admins`.

### Addon capacity packs

- Reseller plan kinds: `subscription` | `addon_volume` | `addon_users`.
- Buying an addon adds capacity only — does **not** change expiry.
- Quick buy (1/5/10…) still available when `allow_buy_extra` is on; extras are
  tracked locally for renew invoices.

### Renew invoice from capacity

- Mode `from_capacity`: `renew_price + extra_gb×unit + extra_users×unit`.
- Mode `fixed`: flat renew price (legacy).
- Amounts recomputed server-side; wallet ledger for renew/addon/extra.

## Deploy

In-panel update to `6.2.5` (runs Alembic `0011_pg_admin_subscription`).
Hard-refresh the panel after update.
