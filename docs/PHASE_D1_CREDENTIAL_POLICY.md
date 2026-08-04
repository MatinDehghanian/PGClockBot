# Phase D1 — Credential / Password Policy Unification

**Status:** Implemented — awaiting approval before D2  
**Branch:** `cursor/phase-d1-credential-policy-b96b`  
**Depends on:** D0 decisions (approved)  
**Does not include:** D2 username sync / dual grant UI, D3 legacy UX, D4 Bot identity, permissions, roles, reseller conversion, bot logic

---

## Approved D0 inputs applied here

| Decision | D1 action |
|----------|-----------|
| Password SoT = PasarGuard | Align validator to PG `PasswordValidator` |
| Digit only if PG requires it | PG requires **≥2 digits** → enforce |
| Same policy on create/update/reset/sync/CLI | Wire every password entrypoint |
| Owner web ≠ PG password by default | No Owner↔env sync; Owner web still uses same *strength* rules |
| No reseller conversion / grant UI change | Untouched |

---

## PasarGuard rules (source)

From PasarGuard `app/models/validators.py` → `PasswordValidator.validate_password`:

- Min **12** characters  
- Max **72** UTF-8 bytes  
- ≥ **2** digits  
- ≥ **2** uppercase `[A-Z]`  
- ≥ **2** lowercase `[a-z]`  
- ≥ **1** special from `!@#$%^&*()-_=+[]{}|;:,.<>?/~``  
- Must not contain `"`  
- Optional: must not contain username  

Current PGClock (`validate_password_strength`): min 8, ≥1 upper/lower/special (any non-alnum), no digit — **weaker than PG**.

---

## D1 design

1. New module `app/services/credential_policy.py` with `validate_password_strength(password, *, username=None) -> (ok, persian_err)` mirroring PG rules + existing placeholder ban.  
2. `web_auth.validate_password_strength` becomes a thin re-export (compat).  
3. Call sites that set/change passwords must use it **before** hash / `modify_admin` / `create_admin` / `save_web_admin`:  
   - `POST /pg/admins` create  
   - `scripts/set_web_password.py`  
   - setup admin, `/security`, staff grant/update/change, reseller provision when pwd set, reseller setup/edit (already mostly wired — verify)  
4. `_rand_password` must always satisfy the unified validator (already close; assert via tests).  
5. UI copy that says «حداقل ۸ کاراکتر» → reflect PG min 12 (templates only, no role/perm changes).  
6. `encrypt_secret` returning `None` on grant/update/change that stores enc → fail the operation (credential integrity; no silent null enc).

**Out of D1:** username equality, grant route → `grant_web_access`, blank-password upgrade conversion behavior beyond encrypt fail-closed, Bot, authz.

---

## Affected files

| File | Change |
|------|--------|
| `app/services/credential_policy.py` | **New** — shared password policy |
| `app/services/web_auth.py` | Re-export / delegate to credential_policy |
| `app/api/pg_pages.py` | Validate password on PG admin create |
| `scripts/set_web_password.py` | Validate before save |
| `app/services/resellers.py` | Ensure `_rand_password` matches; validate in `apply_reseller_panel_password` if missing |
| `app/services/pg_staff_access.py` | Fail if encrypt returns None (grant/update/change) |
| `app/web/templates/pg_admins.html` | Password hint text |
| Other templates with «۸ کاراکتر» password hints | Align copy |
| `tests/test_phase_d1_credential_policy.py` | **New** |
| `docs/PHASE_D1_CREDENTIAL_POLICY.md` | Record |

Likely unchanged callers (already validate via `web_auth`): `app/api/app.py` setup, `app/api/security.py`, `app/api/reseller_pages.py`, `app/api/reseller_setup.py`, `pg_staff_access` strength checks.

---

## Tests

- PG rule parity (min 12, 2 digits, 2 upper, 2 lower, special set, quote ban, 72-byte)  
- Source guards: create_admin route + CLI call validator  
- `_rand_password` samples pass validator  
- encrypt None fails grant  
- C0–C5 / owner-bypass still green (no authz regression)

---

## Stop

After green tests → **stop for D2 approval**.
