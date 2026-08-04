# Phase C — PasarGuard Permission Architecture Analysis

**Status:** STEP 1 — ANALYSIS ONLY (no implementation)  
**Branch:** `cursor/phase-c-permission-analysis-b96b`  
**Codebase baseline:** Phase B tip (`3.8.3` + PostgreSQL/Alembic + global CLI)  
**Rule:** Do not implement until explicit approval of this report.

---

## Executive verdict

PGClock already has substantial authorization hardening (live session refresh, reseller PG credentials, quota gates, shop isolation). It does **not** yet have a single authorization model that makes Web = PasarGuard = Bot.

The largest Phase C risks are architectural:

1. **Two parallel permission systems** — shop feature CSVs vs PasarGuard role-derived page keys.  
2. **pg_staff still uses the Owner PasarGuard client** (`as_owner=True`) for mutations.  
3. **Broad page visibility / `can_write`** can show actions that exact PG actions deny.  
4. **Hosts / nodes / inbounds lists are owner-read and not tenant-filtered.**  
5. **Quota enforcement covers users/traffic/expiry — not HWID/device/resource counts.**  
6. **Bot has no PG capability surface for reseller/pg_staff** (web does).

---

## 1. Current roles

| Role (product language) | First-class in code? | Representation |
|-------------------------|----------------------|----------------|
| **Owner** | No DB enum | `web_admin.json` + env PG credentials / `PG_ACCESS_TOKEN`; web session `role="admin"`; bot `ADMIN_IDS` / `BotUser.role=admin` |
| **Admin** | Yes (`Role.ADMIN`) | Platform bot/web admin; same session role `"admin"` as Owner for web panel |
| **Sub-admin** | **No** | Conceptual only — either `pg_staff` or a reseller-backed PG admin |
| **Reseller** | Yes (`Role.RESELLER`) | `BotUser` + `ResellerProfile` (shop + optional PG admin link) |
| **pg_staff** | Pseudo-role | `PgStaffAccess` table; web session `role="pg_staff"`; **no stored PG password** |

### Details

- DB `Role` enum is only `user | reseller | admin` (`app/db/models.py`).  
- Owner and platform Admin collapse to the same web session role `"admin"`.  
- Persian UI may label pg_staff as «ادمین فرعی», but storage remains `"pg_staff"`.  
- Sub-admin is **not** a model; Phase C must either formalize it or define it as an alias of `pg_staff` / limited PG admin.

---

## 2. Current permission sources

### 2.1 PasarGuard native permissions

Source: PasarGuard admin/role APIs (`pasarguard.py`) → mapped in `pg_access.py`.

**Panel feature keys (sidebar):**

`pg_overview`, `pg_users`, `pg_templates`, `pg_groups`, `pg_hosts`, `pg_inbounds`, `pg_nodes`

**Mapping rule (coarse):** any of several PG actions on a resource ⇒ whole page key (e.g. users create/update/delete ⇒ `pg_users`).

**Fine-grained matrices also exist:**

- User actions: create/read/update/delete/reset_usage/revoke_sub/disable/enable  
- Resource actions: users/templates/groups/hosts/nodes × create/update/delete/reconnect  
- Access limits: `require_template`, `allowed_template_ids`, `allowed_group_ids`

`pg_admins` exists as a label but is **not** in `PG_FEATURE_KEYS` (admin-only route).

### 2.2 Web Panel shop permissions

Source: `ResellerProfile.web_permissions` CSV → `FEATURE_PERMS` in `resellers.py`:

`dashboard`, `plans`, `orders`, `payments`, `tickets`, `stats`, `shop_settings`

Guard: `require_perm()` — Owner/admin bypass; others need key in session/live `permissions`.

### 2.3 Telegram Bot permissions

Source: `ResellerProfile.bot_permissions` CSV → `has_bot_perm()` (thin wrapper over `has_perm()`).

- No shared `require_bot_perm` abstraction.  
- Handlers re-check keys independently.  
- **No bot equivalent of PG role capabilities** for reseller/pg_staff (bot PG tools are platform-admin only).

### 2.4 Database ACL tables / fields

| Store | What it authorizes |
|-------|--------------------|
| `ResellerProfile.web_permissions` / `bot_permissions` | Shop features |
| `ResellerProfile.pg_admin_username` / `pg_admin_password_enc` / `pg_role_id` | PG client identity + role hint |
| `ResellerProfile.bot_admin_ids` | Extra Telegram IDs on dedicated shop bot |
| `ResellerPlan.*_permissions` / `pg_role_id` | Defaults when approving resellers |
| `PgStaffAccess` | Web login for an existing PG admin (no PG password) |
| `Setting` / `ResellerSetting` | Config, not capability ACL |

### 2.5 Session / cookie permissions

Login cookie carries: `role`, `username`, `permissions`, `pg_permissions`, plus optional `bot_user_id`, `pg_admin_username`, `pg_user_actions`, `pg_access`, `pg_writes`, `pg_role_id`, `pv`, admin `sv`.

**Important:** reseller/pg_staff ACLs are **re-read live** on each request in `require_staff()` (DB + PG role refresh). Cookie is identity + cache, not sole authority.

---

## 3. Current permission flow

```text
LOGIN
  ├─ Owner/web_admin.json  → role=admin (full bypass)
  ├─ ResellerProfile web   → role=reseller + shop perms + PG role features
  └─ PgStaffAccess         → role=pg_staff + PG role features only
        │
        ▼
IDENTITY (session cookie signed)
        │
        ▼
PERMISSION RESOLUTION (per request for non-admin)
  ├─ Shop keys from DB CSV
  └─ PG keys/actions/access from live PG role
        │
        ▼
MENU VISIBILITY
  ├─ Web sidebar: permissions ∪ pg_permissions
  └─ Bot keyboard: has_bot_perm(shop keys only)
        │
        ▼
API / HANDLER AUTHORIZATION
  ├─ require_perm / require_pg_perm / require_admin
  ├─ Exact PG action checks on many POSTs
  └─ Quota / provision gates on user create-modify
        │
        ▼
PASARGUARD OPERATION
  ├─ Admin → get_pg() owner client
  ├─ Reseller → get_pg_for_reseller() (own credentials; no owner fallback)
  └─ pg_staff → get_pg() owner client + as_owner=True (+ set_owner on create)
```

### Client selection (`_staff_pg`)

```40:60:app/api/pg_pages.py
async def _staff_pg(session: AsyncSession, staff: dict):
    ...
    if is_platform_admin(staff):
        return get_pg(), True
    rid = shop_owner_id(staff)
    if rid:
        return await get_pg_for_reseller(session, int(rid)), False
    if staff.get("role") == "pg_staff":
        ...
        return get_pg(), True
```

---

## 4. Mismatches identified

### P0 — Security / isolation

| ID | Issue | Evidence |
|----|-------|----------|
| M1 | **pg_staff Owner-client fallback** for mutations | `_staff_pg` returns `get_pg(), True` for pg_staff |
| M2 | **Hosts / nodes / inbounds listed via owner client without tenant filter** | `pg_pages.py` host/node/inbound list paths |
| M3 | **`role_id` silent drop** on PG admin / reseller create | create retries without `role_id`, may still store requested `pg_role_id` |
| M4 | Users/templates/groups often **owner-read then filter** (oracle / over-fetch risk) | list endpoints use `get_pg()` then filter |

### P1 — Parity / UX correctness

| ID | Issue |
|----|-------|
| M5 | **Web ≠ Bot for PG**: web shows PG pages for reseller/pg_staff; bot PG tools are platform-admin only |
| M6 | **Broad `can_write` vs exact action**: UI may show create while POST requires `hosts.create` etc. |
| M7 | Page keys granted from **any** related PG action (create alone can expose read UI) |
| M8 | Support menu mixes role-based panel tickets vs `tickets` permission for customer tickets |
| M9 | Shop FEATURE_PERMS and PG_FEATURE_KEYS are **parallel systems** — no single decision function |

### P2 — Limits incomplete vs PasarGuard

| Limit | Displayed? | Enforced in `pg_quota`? |
|-------|------------|-------------------------|
| Max users | Yes | Yes |
| Per-user traffic min/max | Yes | Yes |
| Per-user expiry min/max | Yes | Yes |
| Admin limited/disabled write gate | Yes | Yes |
| **HWID min/max** | Overview shows | **No** |
| **Device / max devices** | Partial/unclear | **No** |
| Template/group allow-lists | Access filter | Access only (not quota) |
| Hosts / nodes / groups / templates **counts** | No | **No** |
| Inbounds restrictions | Weak | **No** |

### P3 — Policy trade-offs

| ID | Issue |
|----|-------|
| M10 | PG gate **fail-open** when PasarGuard unreachable (`enforce_pg_admin_web_gate`) — availability vs fail-closed |
| M11 | Owner and platform Admin share session role `"admin"` — hard to distinguish Owner-only ops without extra checks |

---

## 5. Proposed Phase C architecture

### 5.1 Goals (binding)

- Web Panel permissions match PasarGuard capabilities (exact actions, not only page keys).  
- Telegram Bot shop permissions match Web shop permissions.  
- Where Bot exposes PG ops, same PG capability matrix as Web.  
- Admin/reseller/pg_staff restrictions enforced consistently.  
- **No Owner fallback for restricted users** (reseller already compliant; pg_staff must change).  
- No privilege escalation / IDOR.  
- Owner workflow preserved.

### 5.2 Unified authorizer

Introduce a single decision object (design name: `AuthzContext` / `authorize()`):

```text
Principal { owner | platform_admin | reseller | pg_staff }
  + ShopCapabilities (FEATURE_PERMS)
  + PgCapabilities (resource × action)
  + PgLimits (users/traffic/expiry/HWID/device + access allow-lists)
  + Scope { shop_owner_id?, pg_admin_username? }
```

Used by:

- Web menus  
- Web API dependencies  
- Bot menus  
- Bot actions  
- PasarGuard client selection + pre-flight checks  

Session role remains identity only; live resolution stays (or short TTL cache).

### 5.3 PasarGuard client policy

| Principal | Client | Rule |
|-----------|--------|------|
| Owner / platform admin | `get_pg()` | Allowed |
| Reseller | `get_pg_for_reseller()` | Required; fail closed if missing password |
| pg_staff | **Own PG credentials/token** (new) | **No owner client for mutations**; fail closed until credentials exist |

Create/edit admin flows must store encrypted PG password (or scoped token) for pg_staff, matching reseller pattern — without weakening Owner isolation.

### 5.4 Exact capability UI

- Replace broad `can_write` with `can.users.create`, `can.hosts.update`, etc.  
- Menu visibility ← **read** capability.  
- Buttons ← **exact action**.  
- Hidden menu ≠ bypassable API (`require_exact_pg_action`).

### 5.5 Limits parity

Centralize in provision/quota layer:

- max users  
- traffic/data min/max  
- expiration min/max  
- HWID min/max  
- device limits (if PG exposes)  
- template required + allow-lists  
- group allow-lists  
- host/node/inbound visibility restrictions (filter **and** deny API)  

Missing limit data on mutate ⇒ **deny** for restricted principals (fail closed). Owner may retain operational flexibility.

### 5.6 Admin create/edit

When creating/editing Owner-granted Admin / Sub-admin / Reseller / pg_staff:

1. Expose all supported PasarGuard role restrictions in UI.  
2. Validate password policy before PG API.  
3. **Never silently drop `role_id`** — surface error.  
4. Persist only the role actually applied; verify with PG read-back.  
5. Sync web/bot shop perms as one mirrored set (or one column).  
6. Store PG credentials securely when the principal must act as itself.

### 5.7 Implementation slices (after approval only)

| Slice | Scope |
|-------|--------|
| C0 | Authz module + exact action guards (no behavior change behind flags) |
| C1 | Replace `can_write` / menu checks; API fail-closed parity |
| C2 | Tenant-safe reads (no unfiltered owner lists for hosts/nodes/inbounds) |
| C3 | pg_staff credentials; remove owner mutation fallback |
| C4 | Quota/HWID/device + admin UI limit fields |
| C5 | Bot authorizer parity for shop (+ PG if exposed) |
| C6 | Regression tests (Owner/Admin/Reseller/pg_staff/Bot/Web) |

### 5.8 Explicit non-goals for Phase C

- Phase D identity unification beyond what is required for authz (password sync policy can wait if credentials already stored).  
- Phase E advanced node ops beyond permission-gated existing reconnect/list.  
- CSP / Stars refund / unrelated UX.

---

## 6. Approval checklist

Please confirm before any Phase C coding:

- [ ] Role model understanding (Owner vs admin session; Sub-admin not first-class)  
- [ ] Accept unified authorizer + exact PG actions  
- [ ] Accept **removing pg_staff owner-client mutation fallback** (requires storing PG credentials/token)  
- [ ] Accept fail-closed for restricted principals when PG unreachable (or specify Owner-only exception)  
- [ ] Accept Bot shop = Web shop; Bot PG surface either parity or explicitly deferred  
- [ ] Approve implementation order C0→C6  

**STOPPING HERE — no code changes for Phase C until approval.**
