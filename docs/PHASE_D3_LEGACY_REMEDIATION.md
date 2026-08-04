# Phase D3 — Legacy Remediation (Implementation)

**Status:** Implemented  
**Branch:** `cursor/phase-d3-legacy-remediation-b96b`  
**Depends on:** D2 grant sync  
**Stop before:** D4 (Bot identity)

---

## Binding decisions

| Q | Choice | Behavior |
|---|--------|----------|
| Q1 | **A** | Align `web_username → pg_username` only when Owner checks «هم‌ترازسازی نام کاربری با پاسارگارد» |
| Q2 | Yes | `scripts/list_pg_staff_remediation.py` — read-only inventory |
| Q3 | Yes | Staff `/pg` overview CTA when enc missing or username mismatched |

**Invariants:** keep `pg_staff`; no reseller conversion; no Owner fallback for staff PG ops; preserve bcrypt web logins; explicit remediation only.

---

## What shipped

### Visibility (`ExistingWebAccess` / `web_access_status_map`)

For `source=pg_staff`:

- `credentials_ready` — `staff_has_stored_pg_password`
- `username_aligned` — lower(web) == lower(pg)
- `needs_remediation` — not ready or not aligned

Owner `/pg/admins` badges: «رمز PG ذخیره‌شده» / «نیاز به همگام‌سازی رمز» / «نام کاربری ناهماهنگ».

### Confirm-align (Q1 A)

`update_web_access(..., confirm_align=False)`:

- If DB `web ≠ pg` and posted web equals PG name without `confirm_align` → **error** (no silent rename).
- With checkbox / `confirm_align=true` → web set to PG name (still D1 password rules; enc sync on password).
- Self-serve `/security` remains error-only on mismatch (D2).

Route: `POST …/web-access/staff` reads `confirm_align` form field.

### Staff overview CTA (Q3)

When `role=pg_staff` and remediation needed:

- Misaligned → ask Owner to remediate (no `/security` CTA).
- Aligned + null enc → CTA link to `/security`.

### Inventory CLI (Q2)

```bash
.venv/bin/python -m scripts.list_pg_staff_remediation
.venv/bin/python -m scripts.list_pg_staff_remediation --needs-remediation
.venv/bin/python -m scripts.list_pg_staff_remediation --json
```

Cohorts: L1 null-enc aligned · L2 null-enc mismatch · L3 healthy · L4 enc+mismatch · L5 inactive.

Never prints secrets. No writes.

---

## Never in D3

- `provision_existing_pg_admin` for remediation  
- Silent staff→reseller conversion  
- Owner `get_pg()` for staff list/mutate  
- Alembic / schema changes  
- D4 Bot identity work  

---

## Operator steps

1. Inventory (`list_pg_staff_remediation` or SQL in plan).  
2. For each active L1/L2/L4: Owner → ویرایش ادمین فرعی → confirm-align if needed → set D1-strong password.  
3. Confirm staff re-login / `pg_credentials_ready` / PG lists work.  
4. Do **not** use «اعطای نماینده» to “fix” staff.  

---

## Tests

`tests/test_phase_d3_legacy_remediation.py` — cohorts, status flags, confirm-align gate, no conversion / no Owner fallback contracts, inventory helpers, UI markers.
