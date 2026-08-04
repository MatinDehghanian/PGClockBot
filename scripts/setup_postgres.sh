#!/usr/bin/env bash
# Provision a local PostgreSQL role/database for PGClock production.
# Usage: sudo bash scripts/setup_postgres.sh [db_name] [db_user] [db_password]
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

sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';
  ELSE
    ALTER ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

# Schema privileges (PG15+)
sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 <<SQL
GRANT ALL ON SCHEMA public TO ${DB_USER};
ALTER DATABASE ${DB_NAME} OWNER TO ${DB_USER};
SQL

echo
echo "PostgreSQL ready."
echo "Add to .env:"
echo "DATABASE_URL=\"postgresql+asyncpg://${DB_USER}:${DB_PASS}@127.0.0.1:5432/${DB_NAME}\""
echo
echo "Then: .venv/bin/python -c 'import asyncio; from app.db.session import init_db; asyncio.run(init_db())'"
