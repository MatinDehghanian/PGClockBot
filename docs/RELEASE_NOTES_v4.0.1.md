# PGClockBot v4.0.1 — Bug Fix & Production Polish

**Base:** v4.0.0 (`3e93a02`)  
**App version:** `4.0.1` (`VERSION` + `app/version.py`)  
**Architecture:** unchanged (Phases A–D). No authz / permission / DB redesign. No Owner fallback.

---

## Root causes fixed

| # | Bug | Root cause | Fix |
|---|-----|------------|-----|
| 1 | `pg_staff` `/pg` 500 after login | `request.session` used without `SessionMiddleware` | Use cookie `staff["username"]` only |
| 2 | Grant/update leaves PG password changed but no local enc | `modify_admin` ran before `encrypt_secret` | Encrypt first; sync PG only if enc succeeds |
| 3 | Editing disabled staff re-enables access | Route passed `is_active=True` on every edit | Pass `is_active=None` on update |
| 4 | Uncredentialed staff could open data pages | Menu clamp only in `_pg_ctx`; `require_pg_perm` used full ACL | Gate with `effective_pg_menu_keys` |
| 5 | Self-serve `/security` could align mismatched username | `change_staff_credentials` had no Owner confirm | Block self-serve when misaligned |
| 6 | `get_pg_for_staff` miss on mixed-case username | Exact string match | `func.lower` / normalize |
| 7 | Orphan `PgStaffAccess` under reseller invisible | Status map preferred reseller only | Badge + revoke CTA |
| 8 | Backup/restore/node long ops had no busy UI | Sync POST, no poll endpoint wired in UI | `/backup/status` + busy forms |
| 9 | Misleading UX copy (Owner, فاز D3, ۸+, mutate, provision) | Leftover phase/internal wording | Persian user-facing copy + structured errors |

---

## Modified files (primary)

- `app/api/pg_pages.py`, `app/api/app.py`, `app/api/backup_pages.py`
- `app/services/pg_staff_access.py`, `pasarguard.py`, `resellers.py`, `platform_identity.py`, `users.py`, `release_notes.py`
- Templates: `pg_home.html`, `pg_admins.html`, `pg_nodes.html`, `pg_users.html`, `_settings_backup.html`, `reseller_setup.html`, `reseller_home.html`
- `VERSION`, `app/version.py`
- Tests: `tests/test_v4_0_1_bugfix_polish.py` (+ assertion updates in D1/D3)

---

## Fixed workflows

- Owner: provision/update pg_staff (encrypt-safe; preserve active; confirm-align)
- `credentials_ready` + menu/page gate for incomplete staff
- pg_staff: `/pg` loads; PasarGuard client after successful provisioning
- Dual grant + refuse staff→reseller conversion (clearer errors)
- Orphan staff row cleanup from admins UI
- Backup create/upload/restore busy + restore status poll
- Node reconnect busy state
- Identity help / security copy for admins

---

## Remaining known limitations

- True cross-API atomic rollback (PG password already changed then DB commit fails) is still not available without a new lifecycle — encrypt-first removes the worst partial failure.
- Owner web password remains independent of `PG_PASSWORD` (by design; full identity unification is out of scope).
- Create-backup progress is request-bound (busy button), not a multi-step JSON progress file.
- Live end-to-end against a production PasarGuard instance was not run in this environment (unit/contract + static route audits only).

---

## Regression test summary

- `tests/test_v4_0_1_bugfix_polish.py` — all pass
- Phase suites: `test_phase_*.py`, `test_pg_*.py`, D1–D4, C1/C5, owner bypass / web access guards — green in CI-equivalent local venv

---

## Deployment notes

1. Backup: `pgclock backup --note "pre-v4.0.1"` (or panel backup).
2. Deploy `main` / tag `v4.0.1` (ensure `VERSION` reads `4.0.1`).
3. Restart service: `sudo systemctl restart pgclockbot` (or panel update).
4. No new Alembic revision — schema unchanged from v4.0.0 (`0002_pg_staff_credentials`).
5. Smoke: Owner grant staff → staff login → `/pg` loads → change password when aligned → backup status poll on settings tab.
6. Remediate any remaining L1/L2 staff: `python -m scripts.list_pg_staff_remediation --needs-remediation`.
