# PGClockBot v8.1.0 — Release Notes

**Tag:** `v8.1.0`  
**App version:** `8.1.0`  
**Restore point:** tag `v8.0.0`

---

## نصب و ادمین محدود

- Setup login for a limited PasarGuard admin uses **GET /api/admin** (own account) first. A 403 on the admin directory is no longer treated as “admin not found / wrong password”.
- Token success means connected. 403/404/405 on optional catalogs (admins, hosts, nodes, templates) is not an outage.

## سقف و منوی زنده

- Hybrid Owner dashboards and PG overview show live user/volume caps as cards, not a warning flash.
- Shop wallet appears on Hybrid Owner `/home` when a BotUser is linked.
- PasarGuard sidebar menus follow the nested live role on `GET /api/admin` (same source as quotas). Revoking node access hides **نود** and the dashboard node tile.
- Leftover `is_sudo` on a non-owner role no longer grants every PasarGuard page.

## پلن‌ها

- Status column: **فعال/خاموش** and **خارج از سقف** sit side by side on wide screens, and wrap with a gap when the column is narrow.

## Deploy

In-panel update to `8.1.0` (no new migration vs `v8.0.0`). Hard-refresh the panel after update.
