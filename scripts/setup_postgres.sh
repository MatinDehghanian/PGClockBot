#!/usr/bin/env bash
# Provision a local PostgreSQL role/database for PGClock production.
# Usage: sudo bash scripts/setup_postgres.sh [db_name] [db_user] [db_password]
#
# Design (learned from VPS failures through v11.0.4):
# - Hex-only passwords applied via SQL DO + format(%L) — never psql -v / :'var'.
# - Loopback HBA uses scram-sha-256 ONLY. Never leave scram-first HBA with an
#   md5-stored password (that exact mismatch caused "password authentication
#   failed" after the v11.0.4 md5 fallback).
# - Always restart the *online* cluster after HBA changes (reload is not enough
#   on some images; NR==1 can be the wrong cluster when 16+18 coexist).
# - Last resort: localhost-only trust for this role so install never blocks
#   (listen_addresses stays localhost — not exposed remotely).
#
# Optional: set PGCLOCK_EMIT_URL_FILE to a path; the DATABASE_URL is written
# there (mode 0600) for the installer to consume without scraping stdout.
set -euo pipefail

DB_NAME="${1:-pgclock}"
DB_USER="${2:-pgclock}"
DB_PASS="${3:-}"
AUTH_MODE="scram" # scram | trust (set after verify). Never "socket" — app needs TCP.

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

# Resolve the cluster that is actually serving (prefer online on 5432).
_cluster_ver() {
  if command -v pg_lsclusters >/dev/null 2>&1; then
    local line
    line="$(pg_lsclusters --no-header 2>/dev/null | awk '$4=="online" && $3=="5432"{print; exit}')"
    if [[ -z "$line" ]]; then
      line="$(pg_lsclusters --no-header 2>/dev/null | awk '$4=="online"{print; exit}')"
    fi
    if [[ -z "$line" ]]; then
      line="$(pg_lsclusters --no-header 2>/dev/null | awk 'NR==1{print; exit}')"
    fi
    awk '{print $1}' <<<"$line"
  fi
}

_cluster_name() {
  if command -v pg_lsclusters >/dev/null 2>&1; then
    local line
    line="$(pg_lsclusters --no-header 2>/dev/null | awk '$4=="online" && $3=="5432"{print; exit}')"
    if [[ -z "$line" ]]; then
      line="$(pg_lsclusters --no-header 2>/dev/null | awk '$4=="online"{print; exit}')"
    fi
    if [[ -z "$line" ]]; then
      line="$(pg_lsclusters --no-header 2>/dev/null | awk 'NR==1{print; exit}')"
    fi
    awk '{print $2}' <<<"$line"
  fi
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
  local ver name
  ver="$(_cluster_ver)"
  name="$(_cluster_name)"
  if [[ -n "${ver:-}" && -n "${name:-}" ]] && command -v pg_ctlcluster >/dev/null 2>&1; then
    pg_ctlcluster "$ver" "$name" restart >/dev/null 2>&1 && return 0
  fi
  if command -v systemctl >/dev/null 2>&1; then
    systemctl restart postgresql >/dev/null 2>&1 && return 0
  fi
  return 0
}

_ensure_cluster_up() {
  local i ver name
  for i in $(seq 1 45); do
    if _pg_socket_ready || _pg_tcp_ready; then
      return 0
    fi
    if command -v systemctl >/dev/null 2>&1; then
      systemctl start postgresql >/dev/null 2>&1 || true
    fi
    ver="$(_cluster_ver)"
    name="$(_cluster_name)"
    if [[ -n "${ver:-}" && -n "${name:-}" ]] && command -v pg_ctlcluster >/dev/null 2>&1; then
      pg_ctlcluster "$ver" "$name" start >/dev/null 2>&1 || true
    fi
    sleep 1
  done
  echo "ERROR: PostgreSQL is not ready (pg_isready failed)." >&2
  return 1
}

_hba_path() {
  local hba
  hba="$(_as_postgres psql -tAc "SHOW hba_file" 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ -n "$hba" && -f "$hba" ]]; then
    printf '%s' "$hba"
    return 0
  fi
  local ver cand
  ver="$(_cluster_ver)"
  if [[ -n "$ver" && -f "/etc/postgresql/${ver}/main/pg_hba.conf" ]]; then
    printf '%s' "/etc/postgresql/${ver}/main/pg_hba.conf"
    return 0
  fi
  for cand in /etc/postgresql/*/main/pg_hba.conf; do
    if [[ -f "$cand" ]]; then
      printf '%s' "$cand"
      return 0
    fi
  done
  return 1
}

# Write loopback rules. $1 = scram | trust
#
# Order matters (first match wins):
#   1) local postgres peer  — so sudo -u postgres psql always works
#   2) our role trust/scram (scoped) on local + 127.0.0.1/::1
#   3) host all scram on loopback
#   4) remainder of prior file (without stale managed/loopback password lines)
#
# Never install a blanket `local all all scram` above postgres peer — that
# locks out admin socket access and aborts provisioning mid-script.
_write_hba() {
  local mode="${1:-scram}"
  local hba tmp method
  hba="$(_hba_path)" || {
    echo "WARNING: could not locate pg_hba.conf" >&2
    return 1
  }
  method="scram-sha-256"
  if [[ "$mode" == "trust" ]]; then
    method="trust"
  fi
  tmp="$(mktemp)"
  {
    echo "# PGClockBot — loopback auth (managed; mode=${mode})"
    echo "local   all             postgres                                peer"
    echo "local   ${DB_NAME}      ${DB_USER}                              ${method}"
    echo "host    ${DB_NAME}      ${DB_USER}      127.0.0.1/32            ${method}"
    echo "host    ${DB_NAME}      ${DB_USER}      ::1/128                 ${method}"
    echo "host    all             all             127.0.0.1/32            scram-sha-256"
    echo "host    all             all             ::1/128                 scram-sha-256"
    echo
    # Keep the rest, drop prior managed lines + duplicate loopback host rules +
    # duplicate postgres-peer / our-role local rules we just wrote.
    grep -v -E \
      '^# PGClockBot — loopback|^[[:space:]]*host[[:space:]]+all[[:space:]]+all[[:space:]]+(127\.0\.0\.1/32|::1/128)[[:space:]]+(scram-sha-256|md5|trust)[[:space:]]*$|^[[:space:]]*host[[:space:]]+'"${DB_NAME}"'[[:space:]]+'"${DB_USER}"'[[:space:]]+(127\.0\.0\.1/32|::1/128)[[:space:]]+(scram-sha-256|md5|trust)[[:space:]]*$|^[[:space:]]*local[[:space:]]+all[[:space:]]+postgres[[:space:]]+peer[[:space:]]*$|^[[:space:]]*local[[:space:]]+'"${DB_NAME}"'[[:space:]]+'"${DB_USER}"'[[:space:]]+(scram-sha-256|md5|trust|peer)[[:space:]]*$' \
      "$hba" 2>/dev/null || true
  } > "$tmp"

  if ! cmp -s "$tmp" "$hba"; then
    cp "$hba" "${hba}.bak.pgclock.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
    cat "$tmp" > "$hba"
    chown postgres:postgres "$hba" 2>/dev/null || true
    chmod 640 "$hba" 2>/dev/null || true
    echo "Updated pg_hba.conf (mode=${mode})." >&2
  fi
  rm -f "$tmp"
}

_ensure_tcp_listener_and_hba() {
  local listen need_restart=0

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

  _as_postgres psql -c "ALTER SYSTEM SET password_encryption = 'scram-sha-256'" >/dev/null 2>&1 || true
  _write_hba scram

  # Always restart so HBA + listen_addresses + password_encryption are live.
  echo "Restarting PostgreSQL to apply listen/hba…" >&2
  _restart_postgres

  local i
  for i in $(seq 1 45); do
    if _pg_tcp_ready && _pg_socket_ready; then
      return 0
    fi
    if _pg_tcp_ready; then
      return 0
    fi
    sleep 1
  done
  echo "ERROR: PostgreSQL is not accepting TCP on 127.0.0.1:5432." >&2
  echo "  listen_addresses=$(_as_postgres psql -tAc "SHOW listen_addresses" 2>/dev/null || echo '?')" >&2
  echo "  cluster=$(_cluster_ver)/$(_cluster_name)" >&2
  return 1
}

_set_role_password_and_db() {
  # Force SCRAM hash (never md5) so it matches scram-sha-256 HBA lines.
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
SET password_encryption = 'scram-sha-256';
DO \$\$
BEGIN
  EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', '${DB_USER}', '${DB_PASS}');
END
\$\$;
SQL
}

_rolpassword_prefix() {
  _as_postgres psql -tAc \
    "SELECT COALESCE(left(rolpassword, 10), '<null>') FROM pg_authid WHERE rolname='${DB_USER}'" \
    2>/dev/null | tr -d '[:space:]' || echo '?'
}

_try_tcp() {
  PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -p 5432 -U "$DB_USER" -d "$DB_NAME" \
    -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>&1
}

_try_socket_password() {
  # Unix socket with password (local scram line).
  PGPASSWORD="$DB_PASS" psql -U "$DB_USER" -d "$DB_NAME" \
    -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>&1
}

_try_tcp_trust() {
  # No password — requires trust HBA for this role on loopback.
  psql -h 127.0.0.1 -p 5432 -U "$DB_USER" -d "$DB_NAME" \
    -w -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>&1
}

_enable_trust_fallback() {
  echo "WARNING: password auth still failing — enabling localhost trust for ${DB_USER} only…" >&2
  _write_hba trust
  _restart_postgres
  local i
  for i in $(seq 1 30); do
    _pg_tcp_ready && break
    sleep 1
  done
  # Keep a scram password on the role for later hardening; trust ignores it.
  _set_role_password_and_db >/dev/null 2>&1 || true
}

_verify_tcp_password() {
  local err prefix
  err="$(mktemp)"

  if _try_tcp 2>"$err"; then
    rm -f "$err"
    AUTH_MODE="scram"
    return 0
  fi

  prefix="$(_rolpassword_prefix)"
  echo "WARNING: TCP scram auth failed (rolpassword prefix=${prefix})." >&2
  cat "$err" >&2 || true

  # Re-stamp SCRAM password + full restart (clears stale md5 hashes from older installs).
  echo "Re-applying SCRAM password and restarting cluster…" >&2
  _write_hba scram
  _set_role_password_and_db
  _restart_postgres
  sleep 1

  if _try_tcp 2>"$err"; then
    rm -f "$err"
    echo "TCP password auth OK after SCRAM re-apply." >&2
    AUTH_MODE="scram"
    return 0
  fi

  # Socket-only success is NOT enough for the app: asyncpg with
  # ?host=/var/run/postgresql fails on many VPS images (Errno 2). Always prefer
  # a TCP DATABASE_URL (127.0.0.1). If password TCP is broken, fall through to trust.
  if _try_socket_password 2>"$err"; then
    echo "Unix-socket password auth OK — but the panel needs TCP; enabling localhost trust…" >&2
  else
    echo "WARNING: socket password auth also failed." >&2
    cat "$err" >&2 || true
  fi

  _enable_trust_fallback
  if _try_tcp_trust 2>"$err"; then
    rm -f "$err"
    echo "Localhost trust auth OK for ${DB_USER} (PG not exposed remotely)." >&2
    AUTH_MODE="trust"
    return 0
  fi

  # Last attempt: scram over TCP again after trust HBA rewrite + password stamp.
  _write_hba scram
  _set_role_password_and_db
  _restart_postgres
  sleep 1
  if _try_tcp 2>"$err"; then
    rm -f "$err"
    echo "TCP password auth OK on final retry." >&2
    AUTH_MODE="scram"
    return 0
  fi

  echo "ERROR: Cannot connect as ${DB_USER} via TCP (127.0.0.1:5432)." >&2
  echo "--- psql error ---" >&2
  cat "$err" >&2 || true
  echo "------------------" >&2
  echo "listen_addresses=$(_as_postgres psql -tAc "SHOW listen_addresses" 2>/dev/null || echo '?')" >&2
  echo "hba_file=$(_hba_path 2>/dev/null || echo '?')" >&2
  echo "cluster=$(_cluster_ver)/$(_cluster_name)" >&2
  echo "rolpassword_prefix=$(_rolpassword_prefix)" >&2
  echo "--- pg_hba head ---" >&2
  head -n 20 "$(_hba_path 2>/dev/null || echo /dev/null)" >&2 || true
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

# Always TCP. Never emit Unix-socket URLs — asyncpg hits Errno 2 on common VPS layouts.
DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS_ENC}@127.0.0.1:5432/${DB_NAME}"

if [[ -n "${PGCLOCK_EMIT_URL_FILE:-}" ]]; then
  umask 077
  rm -f "${PGCLOCK_EMIT_URL_FILE}"
  printf '%s\n' "$DATABASE_URL" > "${PGCLOCK_EMIT_URL_FILE}"
  chmod 600 "${PGCLOCK_EMIT_URL_FILE}" 2>/dev/null || true
fi

echo
echo "PostgreSQL ready (auth=${AUTH_MODE})."
echo "Add to .env:"
echo "DATABASE_URL=\"${DATABASE_URL}\""
echo
echo "Then: .venv/bin/python -c 'import asyncio; from app.db.session import init_db; asyncio.run(init_db())'"
