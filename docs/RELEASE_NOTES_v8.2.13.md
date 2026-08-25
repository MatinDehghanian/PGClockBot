# PGClockBot v8.2.13 — Release Notes

**Tag:** `v8.2.13`  
**App version:** `8.2.13`  
**Restore point:** tag `restore/pre-finance-reports-v8.2.12` (@ `v8.2.12`)

## Finance reports tab

1. **Web `/finance`**
   - New first tab: گزارشات (before رفتار کاربر / سفارشات / پرداخت‌ها / تحویل ناموفق)
   - Period compare strip: امروز · ۷ روز · ۳۰ روز (same language as home periods)
   - Panels: فروش · کاربران · عملیات (deep-links to payments/tickets/delivery/users filters)
   - Payment-method breakdown for delivered orders in the selected period

2. **Security**
   - Explicit `reseller_id` on every report query (`None` = Owner platform only)
   - Staff without resolvable `shop_owner_id` fail closed (no Owner data fallback)
   - Tab gated by existing `orders` / `payments` shop ACL

3. **Responsive**
   - Finance report grids stack on narrow viewports
   - Users ops summary + service column polish on mobile (continuing 8.2.11–12)

4. **Bot parity**
   - Admin ops: «📈 گزارشات» → period toggles (Owner-gated)
   - Reseller hub: same entry when orders/payments allowed; shop-scoped metrics

## Update

In-panel update to `8.2.13` (no new migration). Hard-refresh after update.
