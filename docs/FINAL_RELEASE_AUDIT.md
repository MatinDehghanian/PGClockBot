# Final Release Audit — Phase C/D tip

**Status:** AUDIT ONLY — **no code changes**  
**Audited tip:** `68163de` (`cursor/phase-d4-identity-consistency-b96b`) — C0–C5 + D1–D4  
**Branch (docs):** `cursor/phase-final-release-audit-b96b`  
**Product version file:** `4.0.0` (bumped to match tag `v4.0.0`)  
**Date:** 2026-08-04  

---

## Executive verdict

**No release blockers** for Phase C/D security and identity invariants.

Core authz / isolation / phase suites are **green**. Full-repo pytest reports **29 failures**, all classified as **stale historical tests** or **non-security UI/version debt** — not product regressions of Owner-fallback, shop ACL, or role conversion.

**Release-ready** under documented ops constraints (legacy staff remediation; Web Owner ≠ Bot `ADMIN_IDS` unless both configured).

---

## Test results

| Suite | Result |
|-------|--------|
| Full `tests/` | **969 passed**, **29 failed**, 2 warnings |
| Phase B + C0–C5 + D1–D4 + owner/tenant/shop isolation + security hardening + pg_admin gate | **224 passed**, 0 failed |
| Smoke (baseline, CLI, login, home, reseller access, PG user create, admin PG users) | **51 passed**, 0 failed |
| SQLite→PG ETL (`test_sqlite_to_pg_migration_and_validation`) | **PASS** (alone) |

### Failure classification (29) — not blockers

| Class | Count | Assessment |
|-------|------:|------------|
| Pinned old version strings (3.0–3.6.x vs `VERSION=3.8.3`) | ~10 | Test debt |
| Expect pre-D2 silent staff→reseller / blank-pwd upgrade | 2 (`optional_password_login`) | **Intentional D2 refuse** — product correct |
| Stale source-string contracts (pre-C4/C0/`platform_identity`) | ~6 | Tests need rewrite; behavior covered by phase suites |
| Alembic head expects `0001_baseline` only | 1 | Outdated vs C5 `0002_pg_staff_credentials` |
| UI polish / spacing / appearance / panel guards | ~10 | Non-security; cosmetic test drift |

**Do not treat these 29 as C/D regressions.** Superseding coverage: `tests/test_phase_c*.py`, `tests/test_phase_d*.py`, `test_owner_bypass_guards.py`, `test_tenant_isolation.py`, `test_shop_isolation_3_5_4.py`.

---

## Role verification

| Role | Web | Shop | PG client | Bot | Verdict |
|------|-----|------|-----------|-----|---------|
| **Owner** | `web_admin.json` → `role=admin` | Full | `get_pg()` | Independent `ADMIN_IDS` / `BotUser.admin` | **PASS** (channel split documented D4) |
| **Admin** (platform) | Same session `role=admin` (Q1 deferred) | Full | `get_pg()` | Same as Owner on Bot | **PASS** |
| **pg_staff** | `PgStaffAccess` | None | `get_pg_for_staff` / fail-closed | **None** (web-only) | **PASS** |
| **Reseller** | `ResellerProfile` | C4 `web_permissions` | `get_pg_for_reseller` | Shop bot + ACL parity | **PASS** |

---

## Flow verification

| Flow | Verdict | Evidence |
|------|---------|----------|
| Login / logout | **PASS** | `app/api/app.py` three-way login; cookie clear; gate tests |
| Web permissions | **PASS** | `authz` + `require_perm` / `require_pg_perm`; C0/C4 |
| Bot permissions | **PASS** | `can_shop_feature` / `has_bot_perm` → `web_permissions`; D4 helper |
| PasarGuard access | **PASS** | `_staff_pg` / `staff_pg_read_client`; no Owner fallback for staff/reseller; C1/C2/C5/D4 |
| Credential readiness | **PASS** | `pg_credentials_ready`; overview clamp; D1/D3 |
| Admin create/edit/delete | **PASS** | Owner-only grants; D1 validators; dual staff/reseller routes (D2) |
| Reseller lifecycle | **PASS** | Provision; **refuse-if-staff**; shop ACL |
| pg_staff lifecycle | **PASS** | Grant/update; confirm-align; revoke; remediation badges/CTA/CLI |
| Node operations | **PASS** | Web: mapped `pg_nodes` + own client; Bot: platform admin only |
| Backup / restore | **PASS** | Web/Bot admin-only; engine-aware; Phase A/B |
| CLI commands | **PASS** | `pgclock` status/start/stop/restart/logs/health/backup/restore/migrate/doctor; cwd restore (D4) |
| DB PostgreSQL / SQLite | **PASS** | Alembic `0001`+`0002`; ETL test green; dual-engine backup |

---

## PASS items (security / identity)

1. No Owner credential fallback for reseller / pg_staff PG ops.  
2. Shop Web↔Bot ACL aligned (C4); `bot_permissions` mirror write-only.  
3. Dual grant: PG-only → staff; shop → reseller; no silent conversion.  
4. Username equality + confirm-align for staff remediation (D2/D3).  
5. D1 password policy on create/update/sync/CLI paths.  
6. Bot PG management remains platform-admin-only (Q2).  
7. pg_staff web-only; no shop bot ACL (D4).  
8. Tenant / shop isolation suites green.  
9. Owner-bypass guards green.  
10. Identity matrix + `/security` help present (D4 Q4).

---

## Remaining risks (non-blocking)

| Risk | Severity | Notes |
|------|----------|-------|
| Web Owner ≠ Bot admin unless both configured | Medium (ops) | D4 Q1 deferred by design |
| Legacy `PgStaffAccess` null enc / username mismatch | Medium (ops) | Remediable via D3 inventory + Owner edit |
| Deep-link PG routes may not hard-403 without enc | Low | Data path fail-closed; menus clamp |
| 29 stale full-suite tests | Low (CI noise) | Clean up post-release; do not weaken phase suites |
| Alembic Phase A test pins head=`0001` | Low | Update expectation to `0002` in follow-up |
| Synthetic negative Telegram IDs | Low | Notify path skips; label as internal |
| Live Postgres in CI | Low | Unit/ETL covered; production needs reachable PG |

---

## Release blockers

**None.**

No critical security invariant failure found. No code fix performed (per audit scope).

---

## Merge / ship checklist (ops)

1. Merge Phase C/D stack through D4 (or deploy tip `68163de`).  
2. `alembic upgrade head` (includes `0002_pg_staff_credentials`).  
3. Run `python -m scripts.list_pg_staff_remediation --needs-remediation`; remediate L1/L2/L4.  
4. Confirm Owner web login **and** `ADMIN_IDS` for Bot admin tools.  
5. Prefer green gate: phase + isolation suites (not raw full historical suite until stale tests updated).

---

## Explicit non-goals of this audit

- Fixing stale tests or UI polish failures.  
- Implementing Owner/`ADMIN_IDS` auto-link.  
- Adding Bot PG for reseller/pg_staff.  
- Release packaging / changelog beyond this report.
