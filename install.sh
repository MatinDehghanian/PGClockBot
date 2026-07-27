#!/usr/bin/env bash
# PGClockBot — Easy interactive installer (Ubuntu 22.04+ only)
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${CYAN}➜${NC} $*"; }
ok()    { echo -e "${GREEN}✔${NC} $*"; }
warn()  { echo -e "${YELLOW}!${NC} $*"; }
err()   { echo -e "${RED}✖${NC} $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "==============================================="
echo "   PGClockBot — Interactive Installer"
echo "   Ubuntu 22.04+ only"
echo "==============================================="
echo ""

ask() {
  local prompt="$1"
  local default="${2:-}"
  local var
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " var
    echo "${var:-$default}"
  else
    while true; do
      read -r -p "$prompt: " var
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
    read -r -s -p "$prompt: " var
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
    err "Password must include at least one special character (e.g. ! @ # $ % & *)."
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
  ok "Detected supported OS: ${PRETTY_NAME}"
}

ensure_apt_packages() {
  info "Checking and installing system prerequisites..."
  if ! command -v apt-get >/dev/null 2>&1; then
    err "apt-get not found. This installer requires Ubuntu with apt."
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

  $sudo_cmd apt-get update -y
  $sudo_cmd apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    ca-certificates \
    curl \
    git \
    openssl
  ok "System prerequisites are installed."
}

ensure_python_version() {
  if ! command -v python3 >/dev/null 2>&1; then
    err "python3 is not available after package installation."
    exit 1
  fi
  PY=python3
  PY_VER="$($PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  ok "Python version: $PY_VER"
}

require_ubuntu_22_plus
ensure_apt_packages
ensure_python_version

echo ""
info "Step 1/7 — Telegram bot settings"
BOT_TOKEN="$(ask "Bot token (from BotFather)")"
BOT_USERNAME="$(ask "Bot username without @" "PGClockBot")"
ADMIN_IDS="$(ask "Admin Telegram ID(s), comma-separated")"

echo ""
info "Step 2/7 — PasarGuard API settings"
PG_BASE_URL="$(ask "PasarGuard panel URL" "https://dev.mrclock.website")"
PG_BASE_URL="${PG_BASE_URL%/}"
PG_USERNAME="$(ask "PasarGuard admin username")"
PG_PASSWORD="$(ask_secret "PasarGuard admin password")"

echo ""
info "Step 3/7 — Web panel settings (port 9000 default)"
WEB_PORT="$(ask "Web panel port" "9000")"
WEB_ADMIN_USER="$(ask "Web panel login username" "admin")"
echo "Password policy: at least 8 chars, 1 uppercase letter, 1 special char."
WEB_ADMIN_PASSWORD="$(ask_password "Web panel login password")"
WEB_SECRET="$(gen_secret)"

echo ""
info "Step 4/7 — Optional settings"
PUBLIC_BASE_URL="$(ask "Public HTTPS URL for Mini App (leave empty if not ready)" "")"
CURRENCY="$(ask "Currency label" "تومان")"

echo ""
info "Step 5/7 — Python environment and dependencies"
if [[ ! -d .venv ]]; then
  "$PY" -m venv .venv
  ok "Virtual environment created."
else
  ok "Virtual environment already exists."
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip wheel >/dev/null
pip install -r requirements.txt
ok "Python dependencies installed."

echo ""
info "Step 6/7 — Writing .env"
cat > .env <<EOF
BOT_TOKEN=${BOT_TOKEN}
BOT_USERNAME=${BOT_USERNAME}
ADMIN_IDS=${ADMIN_IDS}
PG_BASE_URL=${PG_BASE_URL}
PG_USERNAME=${PG_USERNAME}
PG_PASSWORD=${PG_PASSWORD}
WEB_HOST=0.0.0.0
WEB_PORT=${WEB_PORT}
WEB_SECRET=${WEB_SECRET}
WEB_ADMIN_USER=${WEB_ADMIN_USER}
WEB_ADMIN_PASSWORD=${WEB_ADMIN_PASSWORD}
DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
WEBHOOK_URL=
WEBHOOK_PATH=/telegram/webhook
PUBLIC_BASE_URL=${PUBLIC_BASE_URL}
CURRENCY=${CURRENCY}
DEFAULT_LOCALE=fa
EOF
chmod 600 .env
mkdir -p data
ok ".env and data directory are ready."

echo ""
info "Step 7/7 — Optional systemd service"
INSTALL_SERVICE="$(ask "Create and enable systemd service? (y/N)" "N")"
if [[ "${INSTALL_SERVICE,,}" == "y" || "${INSTALL_SERVICE,,}" == "yes" ]]; then
  SERVICE_USER="$(ask "Linux user to run service as" "$(whoami)")"
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
    ok "systemd service enabled: pgclockbot"
  else
    if ! command -v sudo >/dev/null 2>&1; then
      err "sudo is required to create the service as non-root user."
      exit 1
    fi
    TMP_SVC="$(mktemp)"
    echo "$SERVICE_CONTENT" > "$TMP_SVC"
    sudo cp "$TMP_SVC" "$SERVICE_PATH"
    sudo systemctl daemon-reload
    sudo systemctl enable --now pgclockbot
    ok "systemd service enabled: pgclockbot"
  fi
fi

echo ""
echo "==============================================="
ok "Installation completed successfully."
echo "==============================================="
echo ""
echo "Web panel:"
echo "  URL:      http://SERVER_IP:${WEB_PORT}"
echo "  Username: ${WEB_ADMIN_USER}"
echo "  Password: (the one you entered)"
echo ""
echo "You can configure texts, buttons, menu layout, cards, plans,"
echo "and most bot behavior directly from the web panel."
echo ""
echo "Manual run:"
echo "  source .venv/bin/activate"
echo "  python run.py"
echo ""

START_NOW="$(ask "Start the bot now? (Y/n)" "Y")"
if [[ "${START_NOW,,}" != "n" && "${START_NOW,,}" != "no" ]]; then
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet pgclockbot 2>/dev/null; then
    ok "systemd service is running. Check logs with: journalctl -u pgclockbot -f"
  else
    info "Starting bot... (Ctrl+C to stop)"
    exec .venv/bin/python run.py
  fi
fi
