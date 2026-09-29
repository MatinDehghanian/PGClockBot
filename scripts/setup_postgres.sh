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

_pg_socket_ready() {
  command -v pg_isready >/dev/null 2>&1 || return 1
  # Unix socket / default peer path (works even when TCP is off).
  sudo -u postgres pg_isready -q 2>/dev/null && return 0
  pg_isready -q 2>/dev/null && return 0
  return 1
}

_pg_tcp_ready() {
  command -v pg_isready >/dev/null 2>&1 || return 1
  pg_isready -h 127.0.0.1 -p 5432 -q 2>/dev/null
}

_pg_reload_or_restart() {
  local need_restart="${1:-0}"
  if [[ "$need_restart" == "1" ]]; then
    # listen_addresses changes require a full restart, not reload.
    if systemctl list-unit-files postgresql.service >/dev/null 2>&1; then
      systemctl restart postgresql >/dev/null 2>&1 || true
    fi
    if command -v pg_ctlcluster >/dev/null 2>&1 && command -v pg_lsclusters >/dev/null 2>&1; then
      local ver name
      ver="$(pg_lsclusters --no-header 2>/dev/null | awk 'NR==1{print $1}')"
      name="$(pg_lsclusters --no-header 2>/dev/null | awk 'NR==1{print $2}')"
      if [[ -n "${ver:-}" && -n "${name:-}" ]]; then
        pg_ctlcluster "$ver" "$name" restart >/dev/null 2>&1 || true
      fi
    fi
  else
    sudo -u postgres psql -c "SELECT pg_reload_conf()" >/dev/null 2>&1 || true
    if systemctl list-unit-files postgresql.service >/dev/null 2>&1; then
      systemctl reload postgresql >/dev/null 2>&1 || true
    fi
  fi
}

_ensure_tcp_listener_and_hba() {
  # Make sure the cluster accepts password auth on loopback TCP.
  # Fresh / minimal images sometimes have listen_addresses='' (socket only)
  # — pg_isready on the socket then succeeds while DATABASE_URL over 127.0.0.1 fails.
  local need_restart=0
  local listen hba conf

  listen="$(sudo -u postgres psql -tAc "SHOW listen_addresses" 2>/dev/null | tr -d '[:space:]' || true)"
  case ",${listen}," in
    *,localhost,*|*,127.0.0.1,*|*,\*,*|*,::1,*)
      ;;
    *)
      echo "Configuring listen_addresses=localhost (was: '${listen:-empty}')…" >&2
      sudo -u postgres psql -v ON_ERROR_STOP=1 -c "ALTER SYSTEM SET listen_addresses = 'localhost'" >/dev/null
      need_restart=1
      ;;
  esac

  hba="$(sudo -u postgres psql -tAc "SHOW hba_file" 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ -z "$hba" || ! -f "$hba" ]]; then
    # Fallback common Ubuntu paths
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
    # Prepend loopback password rules so they win over later reject/ident lines.
    {
      echo "# PGClockBot — loopback password auth (managed)"
      echo "host    all             all             127.0.0.1/32            scram-sha-256"
      echo "host    all             all             ::1/128                 scram-sha-256"
      # Also allow password on local sockets (service may use host=/var/run/postgresql).
      echo "local   all             ${DB_USER}                              scram-sha-256"
      echo
      # Drop prior managed block / duplicate loopback scram lines we may have appended.
      grep -v -E '^# PGClockBot — loopback|^[[:space:]]*host[[:space:]]+all[[:space:]]+all[[:space:]]+(127\.0\.0\.1/32|::1/128)[[:space:]]+(scram-sha-256|md5)[[:space:]]*$|^[[:space:]]*local[[:space:]]+all[[:space:]]+'"${DB_USER}"'[[:space:]]+(scram-sha-256|md5)[[:space:]]*$' "$hba" || true
    } > "$tmp"
    if ! cmp -s "$tmp" "$hba"; then
      cp "$hba" "${hba}.bak.pgclock.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
      cat "$tmp" > "$hba"
      chown postgres:postgres "$hba" 2>/dev/null || true
      chmod 640 "$hba" 2>/dev/null || true
      echo "Updated pg_hba.conf for loopback password auth." >&2
      # hba changes only need reload — but if we already need restart for listen, do that.
      if [[ "$need_restart" != "1" ]]; then
        _pg_reload_or_restart 0
      fi
    fi
    rm -f "$tmp"
  else
    echo "WARNING: could not locate pg_hba.conf" >&2
  fi

  # Prefer scram password storage for new role passwords.
  sudo -u postgres psql -c "ALTER SYSTEM SET password_encryption = 'scram-sha-256'" >/dev/null 2>&1 || true

  if [[ "$need_restart" == "1" ]]; then
    echo "Restarting PostgreSQL to apply listen_addresses…" >&2
    _pg_reload_or_restart 1
  else
    _pg_reload_or_restart 0
  fi

  local i
  for i in $(seq 1 45); do
    if _pg_tcp_ready; then
      return 0
    fi
    sleep 1
  done
  echo "ERROR: PostgreSQL is not accepting TCP on 127.0.0.1:5432 after listen/hba fix." >&2
  echo "  listen_addresses=$(sudo -u postgres psql -tAc "SHOW listen_addresses" 2>/dev/null || echo '?')" >&2
  echo "  ss/lsof: $(ss -ltnp 2>/dev/null | grep -E ':5432\b' || netstat -ltnp 2>/dev/null | grep 5432 || true)" >&2
  return 1
}

# Wait for at least socket readiness, then force TCP loopback usable.
if command -v pg_isready >/dev/null 2>&1; then
  for _ in $(seq 1 45); do
    if _pg_socket_ready || _pg_tcp_ready; then
      break
    fi
    # Cluster may still be starting after apt install.
    systemctl start postgresql >/dev/null 2>&1 || true
    sleep 1
  done
  if ! _pg_socket_ready && ! _pg_tcp_ready; then
    echo "ERROR: PostgreSQL is not ready (pg_isready failed)." >&2
    exit 1
  fi
fi

_ensure_tcp_listener_and_hba

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

# Re-apply password after password_encryption/hba settle (role may pre-exist).
sudo -u postgres psql -v ON_ERROR_STOP=1 \
  -v db_user="$DB_USER" \
  -v db_pass="$DB_PASS" <<'SQL'
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'db_user', :'db_pass')\gexec
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
_tcp_err="$(mktemp)"
if ! PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -p 5432 -U "$DB_USER" -d "$DB_NAME" \
  -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>"$_tcp_err"; then
  echo "ERROR: Cannot connect as ${DB_USER} via TCP (127.0.0.1:5432)." >&2
  echo "--- psql error ---" >&2
  cat "$_tcp_err" >&2 || true
  echo "------------------" >&2
  echo "listen_addresses=$(sudo -u postgres psql -tAc "SHOW listen_addresses" 2>/dev/null || echo '?')" >&2
  echo "hba_file=$(sudo -u postgres psql -tAc "SHOW hba_file" 2>/dev/null || echo '?')" >&2
  rm -f "$_tcp_err"
  exit 1
fi
rm -f "$_tcp_err"

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
