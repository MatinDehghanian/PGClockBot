# PGClockBot v8.5.1 — Release Notes

**Tag:** `v8.5.1`  
**App version:** `8.5.1`  
**Restore point:** tag `restore/pre-ui-preview-users-fix-v8.5.0` (@ `v8.5.0`)

## Fixes

1. **Telegram settings preview**
   - Opens inside the same preview card; «نمایش پیش‌نمایش» hides while open and returns on close
   - Close button is full-width (mobile-friendly)

2. **Users table**
   - Alert = orange dot only; risk = yellow badge (warn tokens)
   - Narrower service column; compact picker matching control/menu radii
   - Menu ported to `body` (avoids `.table-wrap` clip); sort values update on switch
   - Edit modal: `data-user-edit-open` + explicit `openModal`

3. **Finance reports**
   - Removed redundant day/week/month section-tabs (compare cards remain the selector)

4. **Bot**
   - Admin quick renew on user card; platform-shop scope on all admin user paths (search/view/message/wallet/services/block/delete/unreseller)

## Security (pre-release audit)

- Approved for release after scope/ACL/XSS review of users ops, DMs, edit fragment, finance reports/behavior, and bot soft callbacks
- Admin bot: `_platform_shop_user` on sibling user callbacks + wallet/block/message/unreseller FSM saves
- Finance **behavior** tab: fail-closed for non-platform staff without resolvable `shop_owner_id` (same as reports)
- Web user routes remain `assert_bot_user_in_scope`; bulk DM Owner/shop-scoped; preview/message HTML escaped

## Deploy

In-panel update to `8.5.1` (no new migration). Hard-refresh after update.
