# Phase D4 — Web/Bot Identity Consistency (Implementation)

**Status:** Implemented  
**Branch:** `cursor/phase-d4-identity-consistency-b96b`  
**Depends on:** D3  
**Stop before:** Release audit  

**Approved decisions:** Q1 A · Q2 A · Q3 A · Q4 A · Q5 A/B

---

## What shipped

| Item | Detail |
|------|--------|
| Matrix docs | `docs/PHASE_D4_IDENTITY_MATRIX.md` |
| Thin helper | `app/services/platform_identity.py` — web/bot platform-admin predicates, synthetic TG id, FA help |
| Wiring | `bot/auth.is_platform_admin` → helper; `shop_scope.is_platform_admin` → helper |
| Q4 UI | `/security` identity help card (`identity_help_fa`) |
| Q3 | Documented: `bot_permissions` mirror kept; reads still `web_permissions` |
| Q2 | No Bot PG for reseller/pg_staff; contract tests lock `get_pg()`-only in bot admin PG modules |
| Q1 | No `is_owner` session field; `PrincipalKind.OWNER` still unused for ACL |
| Hygiene | Notify path uses `deliverable_telegram_id` / `is_synthetic_telegram_id` |
| CLI | `pgclock` restores caller CWD after `build_context` chdir (test isolation) |
| Tests | `tests/test_phase_d4_identity_consistency.py` |

---

## Invariants held

- No new Bot PG access  
- No Owner fallback for staff/reseller  
- Web/Bot shop ACL remains C4-aligned  
- pg_staff stays web-only  

---

## Tests

- Role boundary contracts (Owner / pg_staff / Reseller)  
- Bot PG handlers: platform admin + `get_pg` only  
- `_staff_pg` / read client: no Owner fallback for restricted roles  
- C4 + C0–C5 + D1–D3 regression must stay green  
