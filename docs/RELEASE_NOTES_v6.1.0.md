# PGClockBot v6.1.0 — Release Notes

**Tag:** `v6.1.0`
**App version:** `6.1.0`

---

## Follow-ups from the v6.0.0 security audit

Two smaller items identified while walking through real-world multi-tenant
scenarios (a limited sub-admin with a 3-group/20-user/100GB cap, and an
owner with 1,000 direct users + 50 sub-admins × 2,000 users each):

### Performance: index on `bot_users.reseller_id`

- Added `index=True` on the ORM column plus Alembic migration
  `0010_bot_users_reseller_id_index` (applies automatically on next
  startup, both SQLite and PostgreSQL).
- Every reseller-scoped query — the bot's "my customers" list, dashboards,
  finance pages, and every tenant-isolation filter added in v6.0.0 — filters
  on this column. Without an index this degrades to a full table scan as
  the platform grows (e.g. tens of thousands of `bot_users` rows across many
  sub-admins).
- Also mirrored into the legacy pre-Alembic SQLite bootstrap path
  (`_ensure_indexes`) for full coverage on very old installs.

### Friendly quota pre-check for Hybrid Owner admins

- `pg_quota.staff_needs_quota_check()` previously skipped the max_users /
  data-cap pre-check for *every* `role="admin"`, including a **Hybrid
  Owner** setup where the platform `.env` PasarGuard account is itself a
  limited admin (`pg_is_owner=False`). That admin would only discover their
  own cap from PasarGuard's raw rejection instead of the same friendly
  Persian message resellers/`pg_staff` already get.
- The gate now only bypasses for a genuine sudo owner (`pg_is_owner` missing
  or `True` — unchanged default); a Hybrid Owner is checked exactly like any
  other restricted admin.
- This single change automatically extends the pre-check to every existing
  web-panel `/pg/users` create/modify/mutate call site (they already thread
  `staff` unconditionally through the provision gate).
- The bot's own PasarGuard user-creation flow — previously never wired to
  `pg_quota` at all — now gets the same pre-check via a new
  `platform_pg_quota_staff()` helper, applied to both the template and
  custom create paths.

## Compatibility

- No breaking changes. The index migration is additive and idempotent; the
  quota-gate change only adds an *earlier, friendlier* rejection for a case
  that would previously have failed later at the PasarGuard API call anyway
  (for the affected Hybrid Owner scope only — full/default owners are
  unaffected).

## Deploy

In-panel update to `6.1.0` (or deploy this tag). The database index is
applied automatically on next startup; no manual migration steps required.
