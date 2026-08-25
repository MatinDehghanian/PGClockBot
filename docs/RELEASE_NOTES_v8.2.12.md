# PGClockBot v8.2.12 — Release Notes

**Tag:** `v8.2.12`  
**App version:** `8.2.12`  
**Restore point:** tag `restore/pre-users-alerts-ops-v8.2.10` (@ `v8.2.10`)

## Completes the users + alerts package (after 8.2.11)

1. **Quick actions on `/users`**
   - Per-row: پیام (modal) · تمدید سریع (critical service + current plan)
   - Filtered bulk message (max 40; Owner/shop-scoped; confirm)
   - Mutations still Owner-only for edit/block/delete; ops allowed for dashboard staff in scope

2. **Action center**
   - Low-volume entry → `/users?filter=low_volume`

3. **Deep-link reuse**
   - Tickets (bot users) + finance orders/payments → `/users?uid=`

4. **Bot parity**
   - Admin: ✉️ پیام + richer user card / web deep-link
   - Reseller: پیام + تمدید سریع on customer card

## Security notes

- Staff DM text is tag-stripped and HTML-escaped
- Bulk requires an active non-`all` filter; recipients rebuilt server-side from shop scope
- Quick renew / message always go through `assert_bot_user_in_scope`

## Update

In-panel update to `8.2.12` (no new migration). Hard-refresh after update.
