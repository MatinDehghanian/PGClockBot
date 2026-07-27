#!/usr/bin/env bash
# PGClockBot — Interactive installer (Ubuntu 22.04+ only)
set -euo pipefail

# ── colors ──────────────────────────────────────────────
R='\033[0;31m'; G='\033[0;32m'; C='\033[0;36m'
Y='\033[1;33m'; B='\033[1;37m'; D='\033[2m'; N='\033[0m'
BOLD='\033[1m'

info()  { echo -e "  ${C}›${N} $*"; }
ok()    { echo -e "  ${G}✔${N} $*"; }
warn()  { echo -e "  ${Y}!${N} $*"; }
err()   { echo -e "  ${R}✖${N} $*" >&2; }
step()  { echo -e "\n${BOLD}${C}── $* ──${N}\n"; }

banner() {
  clear 2>/dev/null || true
  echo -e "${C}"
  cat <<'ART'
   ╔══════════════════════════════════════════╗
   ║                                          ║
   ║          P G C l o c k B o t             ║
   ║     PasarGuard Telegram Shop Installer   ║
   ║                                          ║
   ╚══════════════════════════════════════════╝
ART
  echo -e "${N}"
  echo -e "  ${D}Ubuntu 22.04+  ·  English prompts  ·  Auto setup${N}"
  echo ""
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Escape a value for double-quoted .env assignment
env_quote() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  printf '"%s"' "$s"
}

ask() {
  local prompt="$1"
  local default="${2:-}"
  local var
  if [[ -n "$default" ]]; then
    read -r -p "  ${B}${prompt}${N} ${D}[${default}]${N}: " var
    echo "${var:-$default}"
  else
    while true; do
      read -r -p "  ${B}${prompt}${N}: " var
      if [[ -n "$var" ]]; then
        echo "$var"
        return
      fi
      err "This field is required."
    done
  fi
}

ask_secret() {
  local prompt="$1"
  local var
  while true; do
    read -r -s -p "  ${B}${prompt}${N}: " var
    echo ""
    if [[ -n "$var" ]]; then
      echo "$var"
      return
    fi
    err "This field is required."
  done
}

validate_password() {
  local p="$1"
  if [[ ${#p} -lt 8 ]]; then
    err "Password must be at least 8 characters."
    return 1
  fi
  if ! [[ "$p" =~ [A-Z] ]]; then
    err "Password must include at least one uppercase letter (A-Z)."
    return 1
  fi
  if ! [[ "$p" =~ [^a-zA-Z0-9] ]]; then
    err "Password must include at least one special character (e.g. ! @ # \$ % & *)."
    return 1
  fi
  return 0
}

ask_password() {
  local prompt="$1"
  local p1 p2
  while true; do
    p1="$(ask_secret "$prompt")"
    if ! validate_password "$p1"; then
      continue
    fi
    p2="$(ask_secret "Confirm password")"
    if [[ "$p1" != "$p2" ]]; then
      err "Passwords do not match."
      continue
    fi
    echo "$p1"
    return
  done
}

gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  else
    head -c 48 /dev/urandom | xxd -p | tr -d '\n' | head -c 48
  fi
}

require_ubuntu_22_plus() {
  if [[ ! -f /etc/os-release ]]; then
    err "Unsupported system: /etc/os-release not found."
    exit 1
  fi
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" != "ubuntu" ]]; then
    err "This installer supports Ubuntu only."
    err "Detected: ${PRETTY_NAME:-unknown}"
    exit 1
  fi
  local major
  major="$(echo "${VERSION_ID:-0}" | cut -d. -f1)"
  if [[ -z "$major" || "$major" -lt 22 ]]; then
    err "Ubuntu 22.04 or newer is required."
    err "Detected: ${PRETTY_NAME:-unknown}"
    exit 1
  fi
  ok "OS: ${PRETTY_NAME}"
}

ensure_apt_packages() {
  info "Checking system packages..."
  if ! command -v apt-get >/dev/null 2>&1; then
    err "apt-get not found."
    exit 1
  fi

  local sudo_cmd=""
  if [[ "$(id -u)" -ne 0 ]]; then
    if ! command -v sudo >/dev/null 2>&1; then
      err "sudo is required to install prerequisites."
      exit 1
    fi
    sudo_cmd="sudo"
  fi

  $sudo_cmd apt-get update -y >/dev/null
  $sudo_cmd DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    ca-certificates \
    curl \
    git \
    openssl \
    >/dev/null
  ok "Prerequisites ready (python3, venv, pip, curl, git, openssl)"
}

ensure_python_version() {
  if ! command -v python3 >/dev/null 2>&1; then
    err "python3 is not available."
    exit 1
  fi
  PY=python3
  PY_VER="$($PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  ok "Python ${PY_VER}"
}

write_env() {
  # All values are double-quoted so special chars (!$#&) stay intact
  cat > .env <<EOF
BOT_TOKEN=$(env_quote "$BOT_TOKEN")
BOT_USERNAME=$(env_quote "$BOT_USERNAME")
ADMIN_IDS=$(env_quote "$ADMIN_IDS")
PG_BASE_URL=$(env_quote "$PG_BASE_URL")
PG_USERNAME=$(env_quote "$PG_USERNAME")
PG_PASSWORD=$(env_quote "$PG_PASSWORD")
WEB_HOST="0.0.0.0"
WEB_PORT=$(env_quote "$WEB_PORT")
WEB_SECRET=$(env_quote "$WEB_SECRET")
WEB_ADMIN_USER=$(env_quote "$WEB_ADMIN_USER")
WEB_ADMIN_PASSWORD=$(env_quote "$WEB_ADMIN_PASSWORD")
DATABASE_URL="sqlite+aiosqlite:///./data/bot.db"
WEBHOOK_URL=""
WEBHOOK_PATH="/telegram/webhook"
PUBLIC_BASE_URL=$(env_quote "$PUBLIC_BASE_URL")
CURRENCY=$(env_quote "$CURRENCY")
DEFAULT_LOCALE="fa"
EOF
  chmod 600 .env
}

# ── run ─────────────────────────────────────────────────
banner
require_ubuntu_22_plus
ensure_apt_packages
ensure_python_version

step "1/7  Telegram"
BOT_TOKEN="$(ask "Bot token (from @BotFather)")"
BOT_USERNAME="$(ask "Bot username without @" "PGClockBot")"
ADMIN_IDS="$(ask "Your Telegram numeric ID (admin)")"
# sanitize: digits and commas only
ADMIN_IDS="$(echo "$ADMIN_IDS" | tr -d '[:space:]')"

step "2/7  PasarGuard panel"
PG_BASE_URL="$(ask "PasarGuard panel URL" "https://dev.mrclock.website")"
PG_BASE_URL="${PG_BASE_URL%/}"
PG_USERNAME="$(ask "PasarGuard admin username")"
PG_PASSWORD="$(ask_secret "PasarGuard admin password")"

step "3/7  Web panel"
WEB_PORT="$(ask "Web panel port" "9000")"
WEB_ADMIN_USER="$(ask "Web panel username" "admin")"
echo -e "  ${D}Password rules: 8+ chars, 1 uppercase, 1 special character${N}"
WEB_ADMIN_PASSWORD="$(ask_password "Web panel password")"
WEB_SECRET="$(gen_secret)"

step "4/7  Optional"
PUBLIC_BASE_URL="$(ask "Public HTTPS URL for Mini App (empty = skip)" "")"
CURRENCY="$(ask "Currency label" "تومان")"

step "5/7  Python packages"
if [[ ! -d .venv ]]; then
  "$PY" -m venv .venv
  ok "venv created"
else
  ok "venv exists"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip wheel -q
pip install -r requirements.txt -q
ok "Python dependencies installed"

step "6/7  Configuration file"
write_env
mkdir -p data
ok ".env written (quoted secrets) · data/ ready"

# Quick self-check: reload settings
CHECK_USER="$("$PY" - <<'PY'
from app.config import get_settings
get_settings.cache_clear()
s = get_settings()
print(s.web_admin_user)
print("OK" if s.bot_token and s.admin_ids else "FAIL")
print(",".join(str(i) for i in s.admin_ids))
PY
)"
mapfile -t CHECK_LINES <<< "$CHECK_USER"
if [[ "${CHECK_LINES[1]:-}" != "OK" ]]; then
  err "Config self-check failed. Re-run installer and verify inputs."
  exit 1
fi
ok "Config OK · web user=${CHECK_LINES[0]} · admin_ids=${CHECK_LINES[2]}"

step "7/7  systemd (optional)"
INSTALL_SERVICE="$(ask "Enable systemd service now? (y/N)" "N")"
if [[ "${INSTALL_SERVICE,,}" == "y" || "${INSTALL_SERVICE,,}" == "yes" ]]; then
  SERVICE_USER="$(ask "System user" "$(whoami)")"
  SERVICE_PATH="/etc/systemd/system/pgclockbot.service"
  SERVICE_CONTENT="[Unit]
Description=PGClockBot
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${SCRIPT_DIR}
Environment=PATH=${SCRIPT_DIR}/.venv/bin
ExecStart=${SCRIPT_DIR}/.venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"
  if [[ "$(id -u)" -eq 0 ]]; then
    echo "$SERVICE_CONTENT" > "$SERVICE_PATH"
    systemctl daemon-reload
    systemctl enable --now pgclockbot
  else
    TMP_SVC="$(mktemp)"
    echo "$SERVICE_CONTENT" > "$TMP_SVC"
    sudo cp "$TMP_SVC" "$SERVICE_PATH"
    sudo systemctl daemon-reload
    sudo systemctl enable --now pgclockbot
  fi
  ok "Service enabled: pgclockbot"
fi

echo ""
echo -e "${G}╔══════════════════════════════════════════╗${N}"
echo -e "${G}║         Installation complete            ║${N}"
echo -e "${G}╚══════════════════════════════════════════╝${N}"
echo ""
echo -e "  Web panel:  ${B}http://YOUR_SERVER_IP:${WEB_PORT}${N}"
echo -e "  Username:   ${B}${WEB_ADMIN_USER}${N}"
echo -e "  Password:   ${D}(the one you entered)${N}"
echo ""
echo -e "  ${D}Configure texts, buttons, plans & card from the web panel.${N}"
echo ""
echo -e "  Manual start:"
echo -e "    ${C}source .venv/bin/activate && python run.py${N}"
echo ""

START_NOW="$(ask "Start the bot now? (Y/n)" "Y")"
if [[ "${START_NOW,,}" != "n" && "${START_NOW,,}" != "no" ]]; then
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet pgclockbot 2>/dev/null; then
    ok "systemd is running — logs: journalctl -u pgclockbot -f"
  else
    info "Starting… open Telegram and press /start on your bot"
    exec .venv/bin/python run.py
  fi
fi
