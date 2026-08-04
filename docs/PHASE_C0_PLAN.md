# Phase C0 — Permission Architecture Foundation (PLAN)

**Status:** AWAITING APPROVAL — no implementation until explicit go-ahead  
**Branch (planned):** `cursor/phase-c0-authz-foundation-b96b`  
**Depends on:** Phase C analysis (`docs/PHASE_C_PERMISSION_ANALYSIS.md`) — approved  
**Does not include:** C1 read isolation, C2 writes, C3 quotas, C4 bot/web UI parity, C5 credentials

---

## Goal

Introduce a **single authorization decision layer** so Web, Bot, and API ask the same questions of the same code — without changing observable behavior yet.

After C0:

- One module owns allow/deny decisions for shop features and PG capabilities.
- Existing entry points (`require_perm`, `require_pg_perm`, `has_perm`, `has_bot_perm`, `staff_pg_action`, …) either call into that module or are thin wrappers with **identical outcomes**.
- Owner/admin bypass behavior unchanged.
- No PasarGuard client selection changes.
- No menu/API response shape changes beyond using the shared helpers.

---

## Non-goals (strict)

| Out of scope | Deferred to |
|--------------|-------------|
| Tenant-safe PG reads / stop owner-token lists | C1 |
| Exact write guards / remove pg_staff owner fallback | C2 |
| HWID / device / resource quotas | C3 |
| Bot keyboards matching web menus for PG | C4 |
| Credential storage / username-password sync | C5 |
| Fail-closed PG unreachable policy change | later (decision in C1/C2) |
| Sub-admin as first-class DB role | later / Phase D |

---

## Current state (what C0 consolidates)

Decision logic is scattered today:

| Concern | Today |
|---------|--------|
| Web shop feature | `require_perm` in `app/api/app.py` + session `permissions` |
| Bot shop feature | `has_bot_perm` → `has_perm` in `app/services/resellers.py` |
| Web PG page | `require_pg_perm` + `pg_permissions` |
| Exact PG action | `staff_pg_action` / `staff_user_actions` in `pg_access.py` |
| Platform admin | `role == "admin"` bypass in multiple places |
| Shop tenant id | `shop_scope.py` |

C0 does **not** invent new permission semantics. It **centralizes** the existing semantics.

---

## Proposed design

### New module: `app/services/authz.py`

```text
PrincipalKind = owner | platform_admin | reseller | pg_staff | unknown

AuthzContext
  kind: PrincipalKind
  role: str                         # session / bot role string
  username: str | None
  shop_owner_id: int | None         # reseller bot_user_id
  pg_admin_username: str | None
  pg_role_id: int | None
  shop_permissions: frozenset[str]  # FEATURE_PERMS keys
  pg_permissions: frozenset[str]    # PG_FEATURE_KEYS
  pg_actions: dict[str, dict[str, bool]]
  pg_user_actions: dict[str, bool]
  pg_access: dict                   # template/group allow-lists
  pg_writes: dict[str, bool]        # legacy broad write flags (kept for parity)
```

### Factory (pure; no I/O)

```text
authz_from_staff(staff: dict) -> AuthzContext
authz_from_reseller_profile(profile, *, role=None) -> AuthzContext  # bot path
```

Builds context from already-resolved staff/profile dicts.  
**Does not** fetch PasarGuard roles (that stays in `require_staff` / `resolve_reseller_pg_features` until later phases).

### Decision API (pure; fail-closed for non-admin)

| Function | Meaning (current semantics preserved) |
|----------|----------------------------------------|
| `is_owner_or_platform_admin(ctx)` | `kind in {owner, platform_admin}` — for C0, both map from session `role=="admin"` (Owner not distinguished yet; **no behavior change**) |
| `can_shop(ctx, key)` | admin → True; else `key in shop_permissions` |
| `can_pg_page(ctx, key)` | admin → True; else `key in pg_permissions` |
| `can_pg_action(ctx, resource, action)` | same as `staff_pg_action` |
| `can_pg_user_action(ctx, action)` | same as `staff_user_actions` lookup |
| `shop_owner_id(ctx)` | same as `shop_scope.shop_owner_id` |

Optional thin FastAPI deps (same raise types as today):

```text
require_shop_perm(key)   # wraps can_shop; may replace body of require_perm
require_pg_page(key)     # wraps can_pg_page; may replace body of require_pg_perm
```

### Wiring strategy (behavior-preserving)

1. Implement `authz.py` with decision functions that **mirror** current if-conditions.
2. Change `require_perm` / `require_pg_perm` to call `can_shop` / `can_pg_page` on `authz_from_staff(user)`.
3. Change `has_perm` / `has_bot_perm` to call `can_shop` (or share the same permission-set parsing path).
4. Change `staff_pg_action` / `staff_user_actions` to delegate to `can_pg_*` **or** have `can_pg_*` call them — either direction is fine if tests prove parity; prefer **authz as the source**, helpers as wrappers.
5. **Do not** change templates, bot keyboards, `_staff_pg`, quota, or list filters.

### Owner note

Owner and platform Admin remain indistinguishable at session level (`role="admin"`). C0 will **not** split them. Naming in `PrincipalKind` may include `owner` for future use, but both resolve as full allow for shop/PG checks exactly as today.

---

## Files expected to change (C0 only)

| File | Change |
|------|--------|
| `app/services/authz.py` | **New** — AuthzContext + decision API |
| `app/api/app.py` | `require_perm` / `require_pg_perm` bodies call authz (logic parity) |
| `app/services/resellers.py` | `has_perm` / `has_bot_perm` call authz (or shared helper) |
| `app/services/pg_access.py` | Optional: `staff_pg_action` / `staff_user_actions` delegate to authz |
| `tests/test_phase_c0_authz.py` | **New** — parity + unit tests |
| `docs/PHASE_C0_AUTHZ.md` | Implementation notes + rollback |

**Not touched in C0:** `pg_pages.py` client selection, templates, bot handlers menus, `pg_quota.py`, models, Alembic.

---

## Tests (C0)

Minimum:

1. **Parity matrix** — for fixtures (admin, reseller with/without keys, pg_staff with/without `pg_actions`, empty permissions):
   - `can_shop` ≡ old `require_perm` allow/deny
   - `can_pg_page` ≡ old `require_pg_perm` allow/deny  
   - `can_pg_action` ≡ `staff_pg_action`
2. **Admin bypass** — all shop + PG checks True.
3. **Fail closed** — missing `pg_actions` on non-admin → mutation action False.
4. **Bot path** — `has_bot_perm` / `can_shop` same answer for same profile CSV.
5. **Regression** — existing suite subset that touches auth (`tests/` related to resellers / pg_access / shop_scope) still passes.

After implementation: run C0 tests + relevant regression; report pass/fail.

---

## Rollback

- Revert the C0 commit/branch; no schema migration.
- Authz is additive; if wiring is wrong, revert wrappers to previous inline checks.

---

## Success criteria

- [ ] `app/services/authz.py` exists and is the documented decision API
- [ ] Web deps and Bot helpers use it for allow/deny
- [ ] No intentional UX / PG operation / Owner behavior change
- [ ] Parity tests green
- [ ] Short C0 report: changed files, tests, regression, rollback

---

## Approval checklist

Please confirm before any C0 coding:

- [ ] Accept `app/services/authz.py` as the single decision module
- [ ] Accept behavior-preserving wrappers only (no UI / PG client / quota changes)
- [ ] Accept Owner vs platform Admin remain collapsed in C0
- [ ] Approve starting implementation on `cursor/phase-c0-authz-foundation-b96b`

**STOP — waiting for approval to start C0 implementation.**
