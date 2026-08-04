# PGClockBot 3.8.3 — Full Project Audit Reports

## Architecture report

### System map

| Layer | Components | Entry |
|-------|------------|-------|
| Process | FastAPI web panel + aiogram bot + APScheduler + reseller bot manager | `run.py` → `app/main.py` |
| Web panel | HTML Jinja templates, session cookie auth, CSRF Origin/Referer | `app/api/app.py` + `*_pages.py` |
| Telegram bot | Reply-keyboard hubs, shop/wallet/support, admin/reseller tools | `app/bot/handlers/*` |
| PasarGuard | HTTP client, owner + per-reseller clients, quota/provision gates | `app/services/pasarguard.py`, `pg_quota.py`, `provision_gate.py` |
| Database | SQLAlchemy async (SQLite/Postgres), shop + billing + tickets | `app/db/models.py` |
| AuthN | Web: bcrypt `web_admin.json` + reseller/pg_staff hashes; Bot: DB role + `ADMIN_IDS` | `web_auth.py`, `bot/auth.py` |
| AuthZ | Shared feature keys (`web_permissions`/`bot_permissions`), PG feature map from PG roles | `require_perm` / `require_pg_perm`, `pg_access.py`, `shop_scope.py` |
| Billing | Fixed commission vs PAYG, usage ticks, topup idempotency | `billing.py`, `jobs/scheduler.py` |
| Backup | ZIP + manifest SHA256, restore with progress | `backup.py`, `backup_pages.py` |

### Admin hierarchy

1. **Owner (web admin)** — `web_admin.json`; full panel; Owner PG token for platform ops.
2. **Bot ADMIN_IDS** — bot admin only (not web) unless also DB `admin` role.
3. **Reseller** — shop + optional PG admin link; scoped by `shop_owner_id` / credentials.
4. **pg_staff** — PG sections only via `PgStaffAccess`; no shop scope; no stored PG password.
5. **Legacy** — plaintext web password auto-upgraded to bcrypt on load (3.8.3).

### Shared authorization model (post-audit)

- Web mutations for resellers use **their** PG credentials via `_staff_pg`.
- pg_staff creates via owner client with **as_owner=True** then `set_owner` (no Owner fallback for resellers).
- Ownership checks for resellers no longer probe arbitrary IDs with the Owner token when a DB session is available.
- Bot and web still mirror the same permission key strings; ACL is re-read from DB on every web request.

---

## Security report

### Fixed in 3.8.3

| ID | Severity | Issue | Fix |
|----|----------|-------|-----|
| H1 | High | `str.format` attribute traversal in reseller/admin message templates | `safe_format()` — named `{key}` only |
| C2 | Critical | SSRF: `/api/system` 401/403 accepted as PG API root; redirects forwarded auth | Require OpenAPI body containing `PasarGuard`; `follow_redirects=False` |
| F1 | High | pg_staff create/template/host mutations failed (`_staff_pg` required shop id) | pg_staff → owner client + `as_owner=True` + existing set_owner path |
| F2 | High | Reseller user mutations used Owner token after soft ownership check | Mutations go through `_staff_pg` / reseller credentials |
| F3 | Medium | Owner-token existence oracle on `_assert_owned_user` for resellers | Reseller path uses `get_pg_for_reseller` |
| H2 | High | Billing topup without idempotency key / empty nonce → double credit | Key required; empty nonce rejected |
| M4 | Medium | Backup manifest leaked absolute `db_path` | Relative `data/bot.db` |
| M-legacy | Medium | Plaintext web passwords survived until next login | Auto-upgrade on `load_web_admin` |
| L-stars | Medium | Stars delivery failure silent to admins | ERROR log + admin alert |
| L-delivery | Low | Silent Telegram send failure | ERROR log when notify fails |
| L-logout | Low | GET CSRF logout | POST logout in UI (GET kept); session cookie stays `SameSite=lax` for gateway returns |
| M1 | Medium | CRC32 synthetic TG id collision | Salted disambiguation without reshuffling salt=0 |

### Intentionally unchanged (documented debt)

| Item | Why |
|------|-----|
| CSP `'unsafe-inline'` | Removing requires nonce plumbing across all templates — high UX risk; deferred |
| PG gate fail-open when unreachable | Availability trade-off; add `STRICT_PG_GATE` later |
| In-process rate limits | Reset on restart; prefer reverse-proxy limits in prod |
| Reseller bot tokens plaintext in DB | Needs migration + WEB_SECRET rotation story |
| Stars refund API | Needs product decision for `refundStarPayment` |

### Owner policy

No new Owner fallback was introduced. Reseller shop delivery and mutations continue to prefer reseller PG credentials. pg_staff still lacks a stored PG password, so create uses the documented owner+`set_owner` path (same as prior reseller legacy path), not a silent privilege grant.

---

## Code quality report

- Added shared `app/services/safe_format.py` — single substitution path for operator-controlled templates.
- Bot shop/wallet/start/reply_nav + delivery + notifications + username patterns migrate to `safe_format`.
- `_staff_pg` / `_assert_owned_user` document role-specific credential rules in one place.
- Fixed brittle owner-bypass test fixtures (`order.note`) broken by wholesale quantity parsing.
- Dead/weak `/api/system` probe branch removed.

---

## UX report

| Before | After |
|--------|--------|
| Stars charge succeeds, delivery fails, only user sees error | Admins also get an alert with payment/charge ids |
| Delivery Telegram send fails silently | Logged at ERROR; no fake “all good” assumption in logs |
| Double-click billing topup could credit twice | Nonce required; clear “refresh form” error |
| Logout via GET (CSRF logout) | Panel uses POST form button |
| pg_staff saw empty/error pages on create | Create path works via set_owner |

Business logic (prices, quotas, commission rules, shop isolation) unchanged except where required for security/correctness above.

---

## Regression report

New suite: `tests/test_full_audit_3_8_3.py`

Covered scenarios:

- Owner bypass guards (set_owner fail-closed, provision gate, reseller credentials)
- pg_staff `_staff_pg` as_owner path
- Reseller `_assert_owned_user` does not call Owner `get_user_by_id`
- Safe format injection blocked
- SSRF probe wiring
- Billing idempotency + nonce
- Plaintext→bcrypt upgrade
- Backup relative path
- Session cookie / logout POST
- Stars admin alert wiring
- Synthetic id salt disambiguation

Also re-run: owner bypass, security hardening, PG web gate, tenant isolation, billing, wholesale 3.8.2 fixtures.

---

## Remaining technical debt

1. CSP nonces (remove `'unsafe-inline'`).
2. Optional `STRICT_PG_GATE` for fail-closed when PasarGuard is down.
3. Persist login/bot rate-limit counters.
4. Encrypt reseller `bot_token` at rest + WEB_SECRET rotation/reencrypt tooling.
5. Stars automatic `refundStarPayment` on unrecoverable delivery failure.
6. Stale version pins in older unit tests (`3.6.8` / `3.3.2`) — historical, not runtime.
7. Unify bot vs web permission helpers into one module (keys already shared).
8. Ticket attachment magic-byte validation for archives/office docs.
