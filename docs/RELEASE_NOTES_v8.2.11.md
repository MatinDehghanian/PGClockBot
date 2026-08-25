# PGClockBot v8.2.11 — Release Notes

**Tag:** `v8.2.11`  
**App version:** `8.2.11`  
**Restore point:** tag `restore/pre-users-alerts-ops-v8.2.10` (@ `v8.2.10`)

## What changed

1. **Users table ops**
   - Role badge beside name (no separate نقش column)
   - Service / volume / expire columns (plan-approx + scheduler flags; live PG stays on edit modal)
   - Multi-service dropdown updates volume/expire cells

2. **Filters + summary**
   - Tabs: همه / نزدیک انقضا / حجم کم / بدون سرویس / مسدود / دارای اعلان
   - Three summary cards; urgency sort; deep-link `uid` highlight

3. **Entity-linked alerts**
   - Action center expiring → `/users?filter=expiring`
   - Orange alert-dot beside name while condition active (clears when resolved)

4. **Security / scope**
   - Platform list: `reseller_id IS NULL` only (aligned with mutation ACL)
   - Reseller (dashboard): read-only customers list; mutations remain Owner-only
   - Deep-link `uid` ignored across shop boundaries

5. **Bot parity**
   - Admin users list + reseller customers: 🔔/⏰/📉 flags; same scoped queries

## What this does *not* change

- No migrations
- Live PG volume/expire still on per-user edit modal only

## Update

In-panel update to `8.2.11` (no new migration). Hard-refresh the panel after update.
