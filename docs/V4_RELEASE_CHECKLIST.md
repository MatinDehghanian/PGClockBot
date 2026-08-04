# PGClockBot v4 — Final Release Checklist

**Audience:** Operators deploying Phase C0–C5 + D1–D4  
**Audited tip:** `68163de` (`cursor/phase-d4-identity-consistency-b96b`)  
**Companion:** `docs/FINAL_RELEASE_AUDIT.md` (no release blockers)  
**Product `VERSION` file:** `4.0.0` (must match GitHub tag `v4.0.0` for in-panel update)  
**Mode:** Checklist only — **no code in this document**

Use this as a runbook. Tick every box in order. Prefer **forward remediation** over schema downgrade.

---

## 0. Pre-flight

- [ ] Release candidate includes Phase **C0–C5** and **D1–D4** (or tip ≥ `68163de`).
- [ ] Read `docs/FINAL_RELEASE_AUDIT.md` — confirm **no blockers**.
- [ ] Read `docs/PHASE_D4_IDENTITY_MATRIX.md` — Web Owner ≠ Bot `ADMIN_IDS` unless both set.
- [ ] Maintenance window announced (password sync may change live PasarGuard admin passwords).
- [ ] Access to: install root, `.env`, DB (Postgres or SQLite), systemd (or process manager), Owner web login, Telegram `ADMIN_IDS`.

---

## 1. Backup steps (before anything else)

### 1.1 Application / DB backup

- [ ] From install root, create a full backup:

```bash
pgclock backup --note "pre-v4-release"
# or:
.venv/bin/python -m app.cli.main backup --note "pre-v4-release"
```

- [ ] Confirm archive appears under `data/backups/` (`pgclock backup --list`).
- [ ] Record **backup id** here: `________________`.

### 1.2 Config snapshot

- [ ] Copy `.env` to a secure off-box location (do **not** commit).
- [ ] Copy `data/web_admin.json` (Owner web credentials).
- [ ] Note current Alembic revision (before upgrade):

```bash
cd /path/to/install
.venv/bin/alembic current
# or: pgclock migrate  # only after you are ready — prefer `alembic current` first
```

- [ ] Record current revision: `________________` (expect `0001_baseline` or already `0002_…` if C5 applied).

### 1.3 Optional DB dump (Postgres)

- [ ] If using PostgreSQL, take an engine-native dump as a second copy:

```bash
pg_dump "$DATABASE_URL_OR_CONN" -Fc -f "pgclock-pre-v4-$(date +%Y%m%d).dump"
```

### 1.4 Verify restore path (dry knowledge)

- [ ] Know restore command before continuing:

```bash
pgclock restore <backup_id> -y
# Add --env only if you intentionally restore .env from that archive
```

---

## 2. Database migration steps

Schema is **additive**. C5 adds nullable `pg_staff_access.pg_admin_password_enc` and `pg_role_id`. No credential auto-backfill.

### 2.1 Stop writers (recommended)

- [ ] Stop the service so migrations and deploy are atomic:

```bash
pgclock stop
# or: sudo systemctl stop pgclockbot
```

### 2.2 Apply Alembic

- [ ] Ensure `DATABASE_URL` in `.env` points at the production DB.
- [ ] Upgrade to head:

```bash
cd /path/to/install
.venv/bin/alembic upgrade head
# equivalent: pgclock migrate
```

- [ ] Confirm head revision:

```bash
.venv/bin/alembic current
```

Expected: **`0002_pg_staff_credentials`** (after `0001_baseline`).

### 2.3 Engine notes

| Engine | Notes |
|--------|--------|
| **PostgreSQL** | Preferred. Run Alembic against the live URL. |
| **SQLite** | Supported; legacy alter paths may also add columns — still run `alembic upgrade head`. |
| **SQLite → Postgres ETL** | Only if migrating engines: `pgclock migrate --from-sqlite --source … --target …` (separate project; take backups of both). |

- [ ] Engine in use: `PostgreSQL` / `SQLite` (circle one).

### 2.4 Post-migration sanity

- [ ] `pgclock doctor` — no unexpected DB errors.
- [ ] Spot-check: table `pg_staff_access` has columns `pg_admin_password_enc`, `pg_role_id`.

---

## 3. Deploy steps

- [ ] Deploy/update code to tip ≥ `68163de` (C0–C5 + D1–D4).
- [ ] Install/update deps if required: `.venv/bin/pip install -r requirements.txt`.
- [ ] Confirm `.env` still has: `DATABASE_URL`, `WEB_*`, `PG_*` (Owner PasarGuard), `ADMIN_IDS`, `WEB_SECRET`.
- [ ] Start service:

```bash
pgclock start
# or: sudo systemctl start pgclockbot
pgclock status
pgclock health
```

- [ ] Web panel responds (login page loads).
- [ ] Telegram bot responds to `/start` on main bot (and shop bots if used).

---

## 4. First login checks

### 4.1 Owner (Web)

- [ ] Log in with Owner credentials (`data/web_admin.json`).
- [ ] Open `/security` — identity help card visible (D4).
- [ ] Open `/pg` — Owner overview/stats load via Owner PG client.
- [ ] Open `/pg/admins` — list loads; dual buttons **اعطای ادمین فرعی** / **اعطای نماینده** present (D2).

### 4.2 Bot platform admin

- [ ] Telegram user in `ADMIN_IDS` (or `BotUser.role=admin`) can open admin hub.
- [ ] Confirm: Web Owner login alone does **not** grant Bot admin tools (and vice versa) unless both are configured.

### 4.3 Reseller (if any)

- [ ] Web login with reseller `web_username`.
- [ ] Shop menus match Bot shop menus for same `web_permissions` (C4).
- [ ] PG pages (if linked): data via reseller client — **not** Owner token.
- [ ] Shop bot: reseller hub works; platform-admin PG tools absent on shop bot.

### 4.4 pg_staff (if any)

- [ ] Web login still works even if enc is NULL (hash unchanged).
- [ ] Without enc: overview-only / empty lists / writes denied — **no Owner fallback**.
- [ ] No shop sidebar; no Bot shop/PG identity (web-only).
- [ ] `/security` shows pg_staff identity help.

---

## 5. Legacy remediation checks (D3)

### 5.1 Inventory

- [ ] Run read-only inventory:

```bash
.venv/bin/python -m scripts.list_pg_staff_remediation
.venv/bin/python -m scripts.list_pg_staff_remediation --needs-remediation
```

- [ ] On `/pg/admins`, confirm badges: missing enc / username mismatch.

### 5.2 Cohorts

| Cohort | Action |
|--------|--------|
| **L3** healthy (aligned + enc) | Leave; spot-check one PG list page |
| **L1** null enc, aligned | Owner staff edit → set D1-strong password **or** staff `/security` |
| **L2 / L4** username mismatch | Owner edit → check **هم‌ترازسازی نام کاربری با پاسارگارد** → password if enc missing |
| **L5** inactive | Reactivate or revoke |
| Pre-converted **reseller** | Leave as reseller; fix null enc via reseller password UI if needed |

- [ ] Every **active** L1/L2/L4 row remediated or explicitly deferred with owner sign-off.
- [ ] After remount: staff re-login → `pg_credentials_ready` → mapped PG menus work.
- [ ] **Do not** use «اعطای نماینده» to “fix” staff (refuses if staff row exists).

### 5.3 Grant path smoke (Owner)

- [ ] Legacy `POST …/web-access` hard-fails (obsolete) — use dual routes only.
- [ ] New PG-only staff uses **اعطای ادمین فرعی**.
- [ ] New shop reseller uses **اعطای نماینده** only when no staff row.

---

## 6. Rollback procedure

**Policy:** Prefer **forward fix** (remediation, config, hotfix). Avoid Alembic downgrade past C5 in production.

### 6.1 Application-only rollback (preferred if schema already at `0002`)

1. [ ] `pgclock stop`
2. [ ] Restore previous **code** revision (without dropping DB columns).
3. [ ] Ensure that code build still understands `pg_admin_password_enc` / fail-closed staff clients — **do not** deploy pre-C5 code against a DB that still has staff sessions expecting isolation.
4. [ ] `pgclock start` → `pgclock health`
5. [ ] If needed: `pgclock restore <pre-v4-backup-id> -y` (data). Use `--env` only with care.

### 6.2 Full backup restore

```bash
pgclock stop
pgclock restore <backup_id> -y
# optional: pgclock restore <backup_id> -y --env
pgclock start
pgclock health
```

- [ ] Verify Owner login and one PG list page.
- [ ] Verify Bot admin still works.

### 6.3 Schema downgrade (last resort — high risk)

```bash
# DANGER: drops pg_admin_password_enc / pg_role_id
.venv/bin/alembic downgrade 0001_baseline
```

- [ ] **Only** with a tested backup and awareness that pre-C5 code may reintroduce Owner fallback for staff.
- [ ] **Do not** roll back D2 grant-split behavior in production (silent staff→reseller conversion returns).
- [ ] Sign-off required: `________________` / date `________`.

### 6.4 Abort criteria (stop deploy / roll back)

- [ ] Owner cannot log in after deploy.
- [ ] Staff/reseller PG ops use Owner token (any evidence of fallback).
- [ ] Data loss or failed migration without successful `alembic current` = `0002_…`.
- [ ] Backup missing or unrestorable before migration.

---

## 7. Sign-off

| Role | Name | Date | Initials |
|------|------|------|----------|
| Operator | | | |
| Owner | | | |
| Reviewer | | | |

**Deployed git SHA:** `________________`  
**Alembic revision:** `0002_pg_staff_credentials` confirmed: [ ]  
**Pre-v4 backup id:** `________________`  
**Legacy remediation complete / accepted residual:** [ ]

---

## Quick command cheat sheet

```bash
pgclock backup --note "pre-v4-release"
pgclock backup --list
.venv/bin/alembic upgrade head
.venv/bin/alembic current
pgclock start | stop | status | health | doctor
.venv/bin/python -m scripts.list_pg_staff_remediation --needs-remediation
pgclock restore <backup_id> -y
```
