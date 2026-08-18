# PGClockBot v8.0.0 — Release Notes

**Tag:** `v8.0.0`  
**App version:** `8.0.0`  
**Restore point:** tag `v7.6.8`

---

## دسترسی پاسارگارد

- After PG username/password in the setup wizard, the installer sees **بررسی سطح دسترسی** and a live report of role, menus, and quotas. That snapshot is display-only; runtime ACL always probes live.
- Creating representatives requires real PG `admins.create` (or a true PG owner). Hybrid Owner without it: menus hidden, server denies create/approve.
- `/pg/admins*` is gated by `pg_admins` permission, not page visibility.

## سقف زنده

- User plans, trial, custom-plan ranges, and reseller subscription/addon packages cannot be saved or sold above the actor’s live PG limits.
- Plan screens show live caps and mark out-of-limit saved plans as **خارج از سقف**.

## ربات

- Shop bots stay isolated from the platform-admin PG-user/object/catalog family.
- A bound sub-representative operates on **their own bot** with self-only scope. L1 never uses Owner `get_pg()`.

## Deploy

In-panel update to `8.0.0` (no new migration vs `v7.6.8`). Hard-refresh the panel after update.
