#!/usr/bin/env bash
# Provision a local PostgreSQL role/database for PGClock production.
# Usage: sudo bash scripts/setup_postgres.sh [db_name] [db_user] [db_password]
#
# Identifiers and the password are passed via psql variables and quoted with
# format(%I) / format(%L) — never string-interpolated into SQL.
#
# Optional: set PGCLOCK_EMIT_URL_FILE to a path; the DATABASE_URL is written
# there (mode 0600) for the installer to consume without scraping stdout.
set -euo pipefail

DB_NAME="${1:-pgclock}"
DB_USER="${2:-pgclock}"
DB_PASS="${3:-}"

if [[ -z "$DB_PASS" ]]; then
  # Hex-only charset: safe in URLs without encoding surprises (@ : / # …).
  if command -v openssl >/dev/null 2>&1; then
    DB_PASS="$(openssl rand -hex 16)"
  else
    DB_PASS="$(head -c 32 /dev/urandom | xxd -p | tr -d '\n' | head -c 32)"
  fi
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql not found. Install postgresql + postgresql-client first." >&2
  exit 1
fi

# Basic charset guard (defense in depth; quoting still applied below).
if [[ ! "$DB_NAME" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || [[ ! "$DB_USER" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "ERROR: db_name and db_user must be simple SQL identifiers (letters, digits, underscore)." >&2
  exit 1
fi

# Ensure the cluster is accepting connections (fresh apt install may need a moment).
# Prefer TCP probe — works as root without `sudo -u postgres` pitfalls.
_pg_ready() {
  if command -v pg_isready >/dev/null 2>&1; then
    pg_isready -h 127.0.0.1 -q 2>/dev/null && return 0
    sudo -u postgres pg_isready -q 2>/dev/null && return 0
  fi
  return 1
}

if command -v pg_isready >/dev/null 2>&1; then
  for _ in $(seq 1 45); do
    if _pg_ready; then
      break
    fi
    sleep 1
  done
  if ! _pg_ready; then
    echo "ERROR: PostgreSQL is not ready (pg_isready failed)." >&2
    exit 1
  fi
fi

sudo -u postgres psql -v ON_ERROR_STOP=1 \
  -v db_user="$DB_USER" \
  -v db_pass="$DB_PASS" \
  -v db_name="$DB_NAME" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'db_user', :'db_pass')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'db_user')\gexec
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'db_user', :'db_pass')
WHERE EXISTS (SELECT FROM pg_roles WHERE rolname = :'db_user')\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'db_name', :'db_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db_name')\gexec
SELECT format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', :'db_name', :'db_user')\gexec
SQL

# Schema privileges (PG15+)
sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 \
  -v db_user="$DB_USER" \
  -v db_name="$DB_NAME" <<'SQL'
SELECT format('GRANT ALL ON SCHEMA public TO %I', :'db_user')\gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'db_name', :'db_user')\gexec
SQL

# Percent-encode password for DATABASE_URL (defense in depth even with hex passwords).
DB_PASS_ENC="$(
  DB_PASS="$DB_PASS" python3 - <<'PY'
import os, urllib.parse
print(urllib.parse.quote(os.environ["DB_PASS"], safe=""))
PY
)"
DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS_ENC}@127.0.0.1:5432/${DB_NAME}"

# Verify the app can authenticate over TCP with password (not just peer/socket).
# Fresh clusters sometimes lack a working host scram rule — fail loud here.
if ! PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>&1; then
  echo "WARNING: TCP password auth to 127.0.0.1 failed — checking pg_hba.conf…" >&2
  # Best-effort: ensure scram for local TCP loopback (common Ubuntu default already has this).
  HBA="$(sudo -u postgres psql -tAc "SHOW hba_file" 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ -n "$HBA" && -f "$HBA" ]]; then
    if ! grep -Eq "^[[:space:]]*host[[:space:]]+all[[:space:]]+all[[:space:]]+127\.0\.0\.1/32[[:space:]]+(scram-sha-256|md5)" "$HBA"; then
      echo "host all all 127.0.0.1/32 scram-sha-256" >> "$HBA"
      echo "host all all ::1/128 scram-sha-256" >> "$HBA"
      if command -v pg_ctlcluster >/dev/null 2>&1; then
        ver="$(pg_lsclusters -h 2>/dev/null | awk 'NR==1{print $1}')"
        name="$(pg_lsclusters -h 2>/dev/null | awk 'NR==1{print $2}')"
        if [[ -n "$ver" && -n "$name" ]]; then
          pg_ctlcluster "$ver" "$name" reload 2>/dev/null || true
        fi
      fi
      sudo -u postgres psql -c "SELECT pg_reload_conf()" >/dev/null 2>&1 || true
    fi
  fi
  if ! PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>&1; then
    echo "ERROR: Cannot connect as ${DB_USER} via TCP (127.0.0.1). Check pg_hba.conf and postgresql listen_addresses." >&2
    exit 1
  fi
fi

if [[ -n "${PGCLOCK_EMIT_URL_FILE:-}" ]]; then
  umask 077
  # Create a fresh file as the current user (usually root via sudo). Do not
  # overwrite a foreign-owned pre-created path under sticky /tmp.
  rm -f "${PGCLOCK_EMIT_URL_FILE}"
  printf '%s\n' "$DATABASE_URL" > "${PGCLOCK_EMIT_URL_FILE}"
  chmod 600 "${PGCLOCK_EMIT_URL_FILE}" 2>/dev/null || true
fi

echo
echo "PostgreSQL ready."
echo "Add to .env:"
echo "DATABASE_URL=\"${DATABASE_URL}\""
echo
echo "Then: .venv/bin/python -c 'import asyncio; from app.db.session import init_db; asyncio.run(init_db())'"
