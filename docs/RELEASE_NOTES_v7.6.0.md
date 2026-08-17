# PGClockBot v7.6.0 — Release Notes

**Tag:** `v7.6.0`  
**App version:** `7.6.0`  
**Restore point:** tag `v7.5.0` (v7.5.0)

---

## نمایندگان

- Shop and org representatives share one product surface: `/resellers` («نمایندگان من» / «افزودن نماینده» / «زیرنماینده»). `/principals` redirects there. Identity SoT is still `OrgPrincipal`; `ResellerProfile` is the commercial shop package of the same representative.
- Web, Bot, and PasarGuard use the same Principal scope and capabilities. Owner `get_pg()` stays Owner-only.
- A Sub-Representative with a shop operates on **that shop’s bot** (token/identity). Leftover Telegram binds do not grant Owner-bot access. Disabled L1 parent fail-closes the child.
- Shop-only password reset uses the representative’s own PasarGuard client when Principal/shop credentials exist. Owner-panel provisioning path is unchanged.
- Synthetic / non-positive Telegram ids are not used for auth, ownership, scope, or routing.

Hierarchy engine, max depth (Owner → Representative → Sub-representative), SQLite/PostgreSQL schema, and tag `v7.0.0` are unchanged.

## Deploy

In-panel update to `7.6.0` (no new migration). Hard-refresh the panel after update.
