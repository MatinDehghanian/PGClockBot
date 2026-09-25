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
  DB_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
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
if command -v pg_isready >/dev/null 2>&1; then
  for _ in $(seq 1 30); do
    if sudo -u postgres pg_isready -q 2>/dev/null; then
      break
    fi
    sleep 1
  done
  if ! sudo -u postgres pg_isready -q 2>/dev/null; then
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

DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS}@127.0.0.1:5432/${DB_NAME}"

if [[ -n "${PGCLOCK_EMIT_URL_FILE:-}" ]]; then
  umask 077
  printf '%s\n' "$DATABASE_URL" > "${PGCLOCK_EMIT_URL_FILE}"
  chmod 600 "${PGCLOCK_EMIT_URL_FILE}" 2>/dev/null || true
fi

echo
echo "PostgreSQL ready."
echo "Add to .env:"
echo "DATABASE_URL=\"${DATABASE_URL}\""
echo
echo "Then: .venv/bin/python -c 'import asyncio; from app.db.session import init_db; asyncio.run(init_db())'"
