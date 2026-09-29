#!/usr/bin/env bash
# Provision a local PostgreSQL role/database for PGClock production.
# Usage: sudo bash scripts/setup_postgres.sh [db_name] [db_user] [db_password]
#
# Password is generated as hex-only (or validated as such) and applied via a
# SQL DO block — never through psql -v / :'var' / \gexec, which has failed on
# some VPS images with "password authentication failed" after ALTER ROLE.
#
# Optional: set PGCLOCK_EMIT_URL_FILE to a path; the DATABASE_URL is written
# there (mode 0600) for the installer to consume without scraping stdout.
set -euo pipefail

DB_NAME="${1:-pgclock}"
DB_USER="${2:-pgclock}"
DB_PASS="${3:-}"

if [[ -z "$DB_PASS" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    DB_PASS="$(openssl rand -hex 24)"
  else
    DB_PASS="$(head -c 48 /dev/urandom | xxd -p | tr -d '\n' | head -c 48)"
  fi
fi

# Strip accidental whitespace/newlines from password generators / paste.
DB_PASS="$(printf '%s' "$DB_PASS" | tr -d '[:space:]')"

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql not found. Install postgresql + postgresql-client first." >&2
  exit 1
fi

# Identifiers: SQL-safe. Password: hex-only so it is safe to embed in SQL.
if [[ ! "$DB_NAME" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || [[ ! "$DB_USER" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "ERROR: db_name and db_user must be simple SQL identifiers (letters, digits, underscore)." >&2
  exit 1
fi
if [[ ! "$DB_PASS" =~ ^[0-9a-fA-F]{16,128}$ ]]; then
  echo "ERROR: db password must be 16–128 hex chars (got length ${#DB_PASS})." >&2
  exit 1
fi

_as_postgres() {
  # Always use sudo -u even when already root (sudo_wrap would drop -u).
  sudo -u postgres "$@"
}

_pg_socket_ready() {
  command -v pg_isready >/dev/null 2>&1 || return 1
  _as_postgres pg_isready -q 2>/dev/null && return 0
  pg_isready -q 2>/dev/null && return 0
  return 1
}

_pg_tcp_ready() {
  command -v pg_isready >/dev/null 2>&1 || return 1
  pg_isready -h 127.0.0.1 -p 5432 -q 2>/dev/null
}

_restart_postgres() {
  if command -v pg_ctlcluster >/dev/null 2>&1 && command -v pg_lsclusters >/dev/null 2>&1; then
    local ver name
    ver="$(pg_lsclusters --no-header 2>/dev/null | awk 'NR==1{print $1}')"
    name="$(pg_lsclusters --no-header 2>/dev/null | awk 'NR==1{print $2}')"
    if [[ -n "${ver:-}" && -n "${name:-}" ]]; then
      pg_ctlcluster "$ver" "$name" restart >/dev/null 2>&1 && return 0
    fi
  fi
  if command -v systemctl >/dev/null 2>&1; then
    systemctl restart postgresql >/dev/null 2>&1 && return 0
  fi
  # Last resort: pg_ctl on data directory
  if [[ -d /var/lib/postgresql ]]; then
    _as_postgres pg_ctl -D /etc/postgresql/*/main restart >/dev/null 2>&1 || true
  fi
  return 0
}

_reload_postgres() {
  _as_postgres psql -c "SELECT pg_reload_conf()" >/dev/null 2>&1 || true
  if command -v systemctl >/dev/null 2>&1; then
    systemctl reload postgresql >/dev/null 2>&1 || true
  fi
}

_ensure_cluster_up() {
  local i
  for i in $(seq 1 45); do
    if _pg_socket_ready || _pg_tcp_ready; then
      return 0
    fi
    if command -v systemctl >/dev/null 2>&1; then
      systemctl start postgresql >/dev/null 2>&1 || true
    fi
    if command -v pg_ctlcluster >/dev/null 2>&1 && command -v pg_lsclusters >/dev/null 2>&1; then
      local ver name
      ver="$(pg_lsclusters --no-header 2>/dev/null | awk 'NR==1{print $1}')"
      name="$(pg_lsclusters --no-header 2>/dev/null | awk 'NR==1{print $2}')"
      if [[ -n "${ver:-}" && -n "${name:-}" ]]; then
        pg_ctlcluster "$ver" "$name" start >/dev/null 2>&1 || true
      fi
    fi
    sleep 1
  done
  echo "ERROR: PostgreSQL is not ready (pg_isready failed)." >&2
  return 1
}

_ensure_tcp_listener_and_hba() {
  local need_restart=0
  local listen hba

  listen="$(_as_postgres psql -tAc "SHOW listen_addresses" 2>/dev/null | tr -d '[:space:]' || true)"
  case ",${listen}," in
    *,localhost,*|*,127.0.0.1,*|*,\*,*|*,::1,*)
      ;;
    *)
      echo "Configuring listen_addresses=localhost (was: '${listen:-empty}')…" >&2
      _as_postgres psql -v ON_ERROR_STOP=1 -c "ALTER SYSTEM SET listen_addresses = 'localhost'" >/dev/null
      need_restart=1
      ;;
  esac

  # Prefer SCRAM for new password hashes.
  _as_postgres psql -c "ALTER SYSTEM SET password_encryption = 'scram-sha-256'" >/dev/null 2>&1 || true

  hba="$(_as_postgres psql -tAc "SHOW hba_file" 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ -z "$hba" || ! -f "$hba" ]]; then
    for cand in /etc/postgresql/*/main/pg_hba.conf; do
      if [[ -f "$cand" ]]; then
        hba="$cand"
        break
      fi
    done
  fi

  if [[ -n "$hba" && -f "$hba" ]]; then
    local tmp
    tmp="$(mktemp)"
    {
      echo "# PGClockBot — loopback password auth (managed)"
      echo "host    all             all             127.0.0.1/32            scram-sha-256"
      echo "host    all             all             ::1/128                 scram-sha-256"
      echo "host    all             all             127.0.0.1/32            md5"
      echo "host    all             all             ::1/128                 md5"
      echo
      # Keep the rest, but drop prior managed / duplicate loopback password lines.
      grep -v -E \
        '^# PGClockBot — loopback|^[[:space:]]*host[[:space:]]+all[[:space:]]+all[[:space:]]+(127\.0\.0\.1/32|::1/128)[[:space:]]+(scram-sha-256|md5)[[:space:]]*$' \
        "$hba" || true
    } > "$tmp"
    if ! cmp -s "$tmp" "$hba"; then
      cp "$hba" "${hba}.bak.pgclock.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
      cat "$tmp" > "$hba"
      chown postgres:postgres "$hba" 2>/dev/null || true
      chmod 640 "$hba" 2>/dev/null || true
      echo "Updated pg_hba.conf for loopback password auth." >&2
    fi
    rm -f "$tmp"
  else
    echo "WARNING: could not locate pg_hba.conf" >&2
  fi

  if [[ "$need_restart" == "1" ]]; then
    echo "Restarting PostgreSQL to apply listen_addresses…" >&2
    _restart_postgres
  else
    _reload_postgres
  fi

  local i
  for i in $(seq 1 45); do
    if _pg_tcp_ready; then
      return 0
    fi
    sleep 1
  done
  echo "ERROR: PostgreSQL is not accepting TCP on 127.0.0.1:5432." >&2
  echo "  listen_addresses=$(_as_postgres psql -tAc "SHOW listen_addresses" 2>/dev/null || echo '?')" >&2
  return 1
}

_set_role_password_and_db() {
  # Hex-only password + validated identifiers → safe to embed (no psql -v).
  # DO block is atomic and works whether the role already exists or not.
  _as_postgres psql -v ON_ERROR_STOP=1 <<SQL
SET password_encryption = 'scram-sha-256';
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', '${DB_USER}', '${DB_PASS}');
  ELSE
    EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', '${DB_USER}', '${DB_PASS}');
  END IF;
END
\$\$;
SELECT format('CREATE DATABASE %I OWNER %I', '${DB_NAME}', '${DB_USER}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

  _as_postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 <<SQL
GRANT ALL ON SCHEMA public TO ${DB_USER};
ALTER DATABASE ${DB_NAME} OWNER TO ${DB_USER};
-- Force password again after DB grants (belt and suspenders).
SET password_encryption = 'scram-sha-256';
ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASS}';
SQL
}

_verify_tcp_password() {
  local err
  err="$(mktemp)"
  if PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -p 5432 -U "$DB_USER" -d "$DB_NAME" \
    -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>"$err"; then
    rm -f "$err"
    return 0
  fi

  echo "WARNING: TCP scram auth failed — retrying with md5 password hash…" >&2
  cat "$err" >&2 || true

  # Some images negotiate md5; store an md5 verifier and keep md5 hba lines.
  _as_postgres psql -v ON_ERROR_STOP=1 <<SQL
SET password_encryption = 'md5';
ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASS}';
SQL
  _reload_postgres
  sleep 1

  if PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -p 5432 -U "$DB_USER" -d "$DB_NAME" \
    -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>"$err"; then
    rm -f "$err"
    echo "TCP password auth OK (md5)." >&2
    return 0
  fi

  echo "ERROR: Cannot connect as ${DB_USER} via TCP (127.0.0.1:5432)." >&2
  echo "--- psql error ---" >&2
  cat "$err" >&2 || true
  echo "------------------" >&2
  echo "listen_addresses=$(_as_postgres psql -tAc "SHOW listen_addresses" 2>/dev/null || echo '?')" >&2
  echo "hba_file=$(_as_postgres psql -tAc "SHOW hba_file" 2>/dev/null || echo '?')" >&2
  echo "rolpassword set=$(_as_postgres psql -tAc "SELECT rolpassword IS NOT NULL FROM pg_authid WHERE rolname='${DB_USER}'" 2>/dev/null || echo '?')" >&2
  rm -f "$err"
  return 1
}

# ── main ────────────────────────────────────────────────
_ensure_cluster_up
_ensure_tcp_listener_and_hba
_set_role_password_and_db
_verify_tcp_password

DB_PASS_ENC="$(
  DB_PASS="$DB_PASS" python3 - <<'PY'
import os, urllib.parse
print(urllib.parse.quote(os.environ["DB_PASS"], safe=""))
PY
)"
DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS_ENC}@127.0.0.1:5432/${DB_NAME}"

if [[ -n "${PGCLOCK_EMIT_URL_FILE:-}" ]]; then
  umask 077
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
