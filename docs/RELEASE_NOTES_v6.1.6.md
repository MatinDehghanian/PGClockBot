# PGClockBot v6.1.6 — Release Notes

**Tag:** `v6.1.6`  
**App version:** `6.1.6`

---

## Button colors

- Admin and reseller button-color menus are separated in settings (clear
  section headers; misgrouped `res_*` hub buttons moved under reseller).
- Plan submenus inherit the selected plan-kind color (fixed / custom /
  trial / wholesale, and reseller fixed / PAYG).
- Shop ACL: resellers can only view/save their own `btn_style_*` keys;
  admin-only style keys cannot be smuggled into `ResellerSetting`
  (same class of guard as `notify_*`).

## Deploy

In-panel update to `6.1.6` (or deploy this tag). Hard-refresh the panel.
