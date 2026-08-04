# Phase A — Database Foundation

**Version:** builds on 3.8.3  
**Scope:** PostgreSQL + Alembic + SQLite→PG tooling + engine-aware backup/restore  
**Out of scope:** global CLI, identity sync, permissions parity, node ops

---

## Phase 0 — Baseline (required before cutover)

```bash
# Ensure schema exists (creates/stamps Alembic on current DATABASE_URL)
.venv/bin/python -m scripts.alembic_upgrade

# Create production baseline: ZIP backup + SQLite copy + configs + git/version + restore verify
.venv/bin/python -m scripts.phase0_baseline --note "pre-phase-a"
```

Artifacts land in `data/baselines/phase0-<timestamp>/`:

| File | Purpose |
|------|---------|
| `BASELINE.json` | Git commit, version, hashes, restore verification |
| `pgclock-backup-*.zip` | Full archive |
| `bot.db` | Explicit SQLite copy |
| `config/env` | `.env` snapshot |
| `config/web_admin.json` | Owner credentials (if present) |

Restore verification is a **sandbox dry-run** (live data is not overwritten).

---

## Phase A — PostgreSQL production setup

```bash
sudo bash scripts/setup_postgres.sh pgclock pgclock
# prints DATABASE_URL=postgresql+asyncpg://...

# Put that URL in .env, then:
.venv/bin/python -m scripts.alembic_upgrade
```

Recommended `.env`:

```env
DATABASE_URL="postgresql+asyncpg://pgclock:SECRET@127.0.0.1:5432/pgclock"
```

Installer: set `PGCLOCK_DATABASE_URL` before `bash pgclock.sh install` to write PostgreSQL into `.env`. Otherwise install still scaffolds SQLite for zero-config labs.

---

## Alembic

```bash
.venv/bin/python -m scripts.alembic_upgrade          # upgrade head
.venv/bin/python -m scripts.alembic_upgrade --current
.venv/bin/python -m scripts.alembic_upgrade --downgrade
```

Baseline revision: `0001_baseline` (full schema from `app.db.models` + `uq_wallet_referral_reason`).

`init_db()` on startup:

1. If tables exist but `alembic_version` missing → legacy additive migrator once → `stamp head`
2. Else → `alembic upgrade head`
3. `create_all` only as emergency fallback (empty DB / `PGCLOCK_ALLOW_CREATE_ALL=1`)

---

## SQLite → PostgreSQL migration

```bash
# 1) Phase 0 baseline first
.venv/bin/python -m scripts.phase0_baseline

# 2) Prepare empty PostgreSQL + schema
sudo bash scripts/setup_postgres.sh
.venv/bin/python -m scripts.migrate_sqlite_to_pg \
  --source 'sqlite+aiosqlite:////ABS/PATH/data/bot.db' \
  --target 'postgresql+asyncpg://pgclock:SECRET@127.0.0.1:5432/pgclock'

# 3) Point .env DATABASE_URL at PostgreSQL and restart service
```

Validation compares row counts, settings keys, wallet/billing sums, and reports VARCHAR overflows.

---

## Engine-aware backup / restore

| Engine | Archive member | Tool |
|--------|----------------|------|
| SQLite | `data/bot.db` | SQLite backup API |
| PostgreSQL | `data/postgres.dump` | `pg_dump -Fc` / `pg_restore` |

Manifest field `db_engine` is required. Restore **refuses** engine mismatch (SQLite archive vs PostgreSQL `DATABASE_URL` and vice versa).

---

## Rollback

1. Stop service  
2. Restore `.env` `DATABASE_URL` to SQLite (from Phase 0 `config/env`)  
3. Restore `data/bot.db` from Phase 0 copy or ZIP  
4. Start service  
5. Keep the abandoned PostgreSQL DB for forensics (do not drop immediately)

Alembic downgrade: `.venv/bin/python -m scripts.alembic_upgrade --downgrade` (drops baseline schema — destructive).

---

## Phase 0 verification (this branch)

Executed in the migration environment before Phase A merge:

```text
.venv/bin/python -m scripts.phase0_baseline --note "phase0-verified-before-phase-a"
→ ok=true, restore_verification.ok=true, sqlite tables_sample present
.venv/bin/python -m scripts.migrate_sqlite_to_pg … → ok=true, counts matched
pytest tests/test_phase0_baseline.py tests/test_phase_a_database.py → 6 passed
```
