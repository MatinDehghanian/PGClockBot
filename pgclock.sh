#!/usr/bin/env bash
# PGClockBot — single entry CLI (Ubuntu 22.04+)
# Usage:
#   bash pgclock.sh
#   bash pgclock.sh install|update|env|web|service|uninstall|status|help
set -euo pipefail
set +H

# curl|bash leaves stdin as a dead pipe. For interactive menus, attach to TTY.
# `install` / `update` / `status` / `help` can run without a TTY.
_CMD="${1:-}"
if [[ ! -t 0 ]]; then
  case "${_CMD}" in
    install|i|update|u|status|s|help|h|-h|--help) ;;
    *)
      if [[ -r /dev/tty ]]; then
        exec </dev/tty
      else
        echo "  x No interactive terminal (TTY). Run: bash pgclock.sh install" >&2
        exit 1
      fi
      ;;
  esac
fi
unset _CMD

R=$'\033[0;31m'; G=$'\033[0;32m'; C=$'\033[0;36m'
Y=$'\033[1;33m'; B=$'\033[1;37m'; D=$'\033[2m'; N=$'\033[0m'
BOLD=$'\033[1m'

info()  { printf '  %s>%s %s\n' "$C" "$N" "$*" > /dev/tty; }
ok()    { printf '  %s+%s %s\n' "$G" "$N" "$*" > /dev/tty; }
warn()  { printf '  %s!%s %s\n' "$Y" "$N" "$*" > /dev/tty; }
err()   { printf '  %sx%s %s\n' "$R" "$N" "$*" > /dev/tty; }
step()  { printf '\n%s%s-- %s --%s\n\n' "$BOLD" "$C" "$*" "$N" > /dev/tty; }
pause() {
  printf '\n  Press Enter to continue... ' > /dev/tty
  read -r _ < /dev/tty || true
}

prompt_read() {
  # Always talk to the real terminal — prompts must NOT go to stdout
  # (values are captured with VAR="$(ask ...)")
  # -e enables readline so Backspace / arrows work when editing mistakes
  local __var="$1"
  shift
  printf '%b' "$*" > /dev/tty
  if ! read -e -r "$__var" < /dev/tty; then
    printf -v "$__var" '%s' ""
  fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
SERVICE_NAME="pgclockbot"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
PY="${SCRIPT_DIR}/.venv/bin/python"
PIP="${SCRIPT_DIR}/.venv/bin/pip"

# ── helpers ─────────────────────────────────────────────
ask() {
  local prompt="$1"
  local has_default=0
  local default=""
  if [[ $# -ge 2 ]]; then
    has_default=1
    default="$2"
  fi
  local var
  if [[ "$has_default" -eq 0 ]]; then
    while true; do
      prompt_read var "  ${B}${prompt}${N}: "
      if [[ -n "${var}" ]]; then
        printf '%s\n' "$var"
        return
      fi
      err "This field is required."
    done
  else
    if [[ -n "$default" ]]; then
      prompt_read var "  ${B}${prompt}${N} ${D}[${default}]${N}: "
    else
      prompt_read var "  ${B}${prompt}${N} ${D}[Enter to skip]${N}: "
    fi
    if [[ -z "${var}" ]]; then
      printf '%s\n' "$default"
    else
      printf '%s\n' "$var"
    fi
  fi
}

ask_optional() {
  local prompt="$1"
  local var=""
  prompt_read var "  ${B}${prompt}${N} ${D}[Enter to skip]${N}: "
  printf '%s\n' "${var}"
}

ask_secret() {
  local prompt="$1"
  local var
  while true; do
    printf '  %b: ' "${B}${prompt}${N}" > /dev/tty
    read -r -s var < /dev/tty || true
    printf '\n' > /dev/tty
    # strip accidental CR / leading-trailing whitespace from paste
    var="${var//$'\r'/}"
    var="${var#"${var%%[![:space:]]*}"}"
    var="${var%"${var##*[![:space:]]}"}"
    if [[ -n "$var" ]]; then
      printf '%s\n' "$var"
      return
    fi
    err "This field is required."
  done
}

ask_password() {
  local prompt="$1"
  local p1 p2
  while true; do
    p1="$(ask_secret "$prompt")"
    p2="$(ask_secret "Confirm password")"
    if [[ "$p1" != "$p2" ]]; then
      err "Passwords do not match."
      continue
    fi
    printf '%s\n' "$p1"
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

sudo_wrap() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

ask_yn() {
  # ask_yn "Prompt" Y|N
  local prompt="$1"
  local default="${2:-N}"
  local hint var
  if [[ "${default^^}" == "Y" ]]; then
    hint="Y/n"
  else
    hint="y/N"
  fi
  prompt_read var "  ${B}${prompt}${N} ${D}[${hint}]${N}: "
  if [[ -z "${var}" ]]; then
    var="$default"
  fi
  case "${var,,}" in
    y|yes) return 0 ;;
    *) return 1 ;;
  esac
}

detect_server_ip() {
  local ip=""
  ip="$(curl -4 -fsS --max-time 4 https://api.ipify.org 2>/dev/null || true)"
  if [[ -z "$ip" ]]; then
    ip="$(curl -4 -fsS --max-time 4 https://ifconfig.me 2>/dev/null || true)"
  fi
  if [[ -z "$ip" ]]; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  fi
  if [[ -z "$ip" ]]; then
    ip="YOUR_SERVER_IP"
  fi
  printf '%s\n' "$ip"
}

web_username() {
  if [[ -f data/web_admin.json ]] && [[ -f "$PY" || -x "$PY" ]]; then
    "$PY" - <<'PY' 2>/dev/null || echo admin
from app.services.web_auth import load_web_admin
print(load_web_admin().get("username") or "admin")
PY
  else
    env_get WEB_ADMIN_USER admin
  fi
}

print_success() {
  # print_success "Title" [extra lines...]
  local title="$1"
  shift || true
  local port ip user
  port="$(env_get WEB_PORT "${WEB_PORT:-9000}")"
  ip="$(detect_server_ip)"
  user="$(web_username)"
  {
    echo ""
    printf '%s==========================================%s\n' "$G" "$N"
    printf '%s  SUCCESS · %s%s\n' "$G" "$title" "$N"
    printf '%s==========================================%s\n' "$G" "$N"
    printf '  Web panel:  %shttp://%s:%s/%s\n' "$B" "$ip" "$port" "$N"
    printf '  Health:     %shttp://127.0.0.1:%s/health%s\n' "$B" "$port" "$N"
    if [[ -f data/setup_complete.flag ]]; then
      printf '  Username:   %s%s%s\n' "$B" "$user" "$N"
    else
      printf '  Next step:  %sopen the URL above (first time = setup wizard)%s\n' "$B" "$N"
    fi
    if [[ $# -gt 0 ]]; then
      echo ""
      local line
      for line in "$@"; do
        printf '  %b\n' "$line"
      done
    fi
    printf '%s==========================================%s\n' "$G" "$N"
    echo ""
  } > /dev/tty
}

require_ubuntu_22_plus() {
  if [[ ! -f /etc/os-release ]]; then
    err "Unsupported system: /etc/os-release not found."
    return 1
  fi
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" != "ubuntu" ]]; then
    err "This tool supports Ubuntu only. Detected: ${PRETTY_NAME:-unknown}"
    return 1
  fi
  local major
  major="$(echo "${VERSION_ID:-0}" | cut -d. -f1)"
  if [[ -z "$major" || "$major" -lt 22 ]]; then
    err "Ubuntu 22.04 or newer is required. Detected: ${PRETTY_NAME:-unknown}"
    return 1
  fi
  ok "OS: ${PRETTY_NAME}"
}

ensure_apt_packages() {
  info "Checking system packages..."
  if ! command -v apt-get >/dev/null 2>&1; then
    err "apt-get not found."
    return 1
  fi
  export DEBIAN_FRONTEND=noninteractive
  sudo_wrap apt-get update -y >/dev/null
  sudo_wrap apt-get install -y \
    python3 python3-venv python3-pip ca-certificates curl git openssl nano \
    >/dev/null
  ok "Prerequisites ready"
}

ensure_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    err "python3 is not available."
    return 1
  fi
  SYSTEM_PY=python3
  ok "Python $($SYSTEM_PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
}

ensure_venv() {
  if [[ ! -d .venv ]]; then
    info "Creating virtualenv..."
    "$SYSTEM_PY" -m venv .venv
    ok "venv created"
  else
    ok "venv exists"
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  local hash_file=".venv/.requirements.sha256"
  local new_hash=""
  if command -v sha256sum >/dev/null 2>&1; then
    new_hash="$(sha256sum requirements.txt | awk '{print $1}')"
  elif command -v shasum >/dev/null 2>&1; then
    new_hash="$(shasum -a 256 requirements.txt | awk '{print $1}')"
  fi
  if [[ -n "$new_hash" && -f "$hash_file" && "$(cat "$hash_file" 2>/dev/null)" == "$new_hash" && -x .venv/bin/python ]]; then
    ok "Python dependencies unchanged (skip pip)"
  else
    if [[ ! -f "$hash_file" ]]; then
      pip install -U pip wheel -q --disable-pip-version-check --no-input || true
    fi
    pip install -r requirements.txt -q --disable-pip-version-check --no-input
    if [[ -n "$new_hash" ]]; then
      printf '%s\n' "$new_hash" > "$hash_file"
    fi
    ok "Python dependencies installed"
  fi
  PY="${SCRIPT_DIR}/.venv/bin/python"
  PIP="${SCRIPT_DIR}/.venv/bin/pip"
}

service_installed() {
  [[ -f "$SERVICE_PATH" ]] || systemctl list-unit-files 2>/dev/null | grep -q "^${SERVICE_NAME}.service"
}

service_active() {
  systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null
}

env_get() {
  local key="$1"
  local fallback="${2:-}"
  if [[ ! -f .env ]]; then
    printf '%s\n' "$fallback"
    return
  fi
  local line
  line="$(grep -E "^${key}=" .env | tail -n1 || true)"
  if [[ -z "$line" ]]; then
    printf '%s\n' "$fallback"
    return
  fi
  local val="${line#*=}"
  val="${val%\"}"
  val="${val#\"}"
  val="${val%\'}"
  val="${val#\'}"
  printf '%s\n' "$val"
}

write_env_file() {
  local py="${PY:-}"
  if [[ -z "$py" || ! -x "$py" ]]; then
    py="${SYSTEM_PY:-python3}"
  fi
  WEB_ADMIN_PASSWORD="$WEB_ADMIN_PASSWORD" \
  BOT_TOKEN="$BOT_TOKEN" \
  BOT_USERNAME="$BOT_USERNAME" \
  ADMIN_IDS="$ADMIN_IDS" \
  PG_BASE_URL="$PG_BASE_URL" \
  PG_USERNAME="$PG_USERNAME" \
  PG_PASSWORD="$PG_PASSWORD" \
  WEB_PORT="$WEB_PORT" \
  WEB_SECRET="$WEB_SECRET" \
  WEB_ADMIN_USER="$WEB_ADMIN_USER" \
  PUBLIC_BASE_URL="$PUBLIC_BASE_URL" \
  CURRENCY="$CURRENCY" \
  "$py" - <<'PY'
import json, os, subprocess, sys
from pathlib import Path
payload = {
    "BOT_TOKEN": os.environ["BOT_TOKEN"],
    "BOT_USERNAME": os.environ["BOT_USERNAME"],
    "ADMIN_IDS": os.environ["ADMIN_IDS"],
    "PG_BASE_URL": os.environ["PG_BASE_URL"],
    "PG_USERNAME": os.environ["PG_USERNAME"],
    "PG_PASSWORD": os.environ["PG_PASSWORD"],
    "WEB_HOST": "0.0.0.0",
    "WEB_PORT": os.environ["WEB_PORT"],
    "WEB_SECRET": os.environ["WEB_SECRET"],
    "WEB_ADMIN_USER": os.environ["WEB_ADMIN_USER"],
    "WEB_ADMIN_PASSWORD": os.environ["WEB_ADMIN_PASSWORD"],
    "DATABASE_URL": f"sqlite+aiosqlite:///{Path.cwd() / 'data' / 'bot.db'}",
    "WEBHOOK_URL": "",
    "WEBHOOK_PATH": "/telegram/webhook",
    "PUBLIC_BASE_URL": os.environ.get("PUBLIC_BASE_URL", ""),
    "CURRENCY": os.environ.get("CURRENCY", "Toman"),
    "DEFAULT_LOCALE": "fa",
}
proc = subprocess.run(
    [sys.executable, str(Path("scripts/write_env.py"))],
    input=json.dumps(payload),
    text=True,
    check=True,
    capture_output=True,
)
print(proc.stdout.strip())
PY
}

install_systemd() {
  local service_user="${1:-$(whoami)}"
  local content
  content="[Unit]
Description=PGClockBot — PasarGuard Telegram shop
After=network.target

[Service]
Type=simple
User=${service_user}
WorkingDirectory=${SCRIPT_DIR}
Environment=PATH=${SCRIPT_DIR}/.venv/bin
ExecStart=${SCRIPT_DIR}/.venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"
  local tmp
  tmp="$(mktemp)"
  printf '%s\n' "$content" > "$tmp"
  sudo_wrap cp "$tmp" "$SERVICE_PATH"
  rm -f "$tmp"
  sudo_wrap systemctl daemon-reload
  sudo_wrap systemctl enable --now "$SERVICE_NAME"
  ok "systemd service enabled: ${SERVICE_NAME}"
}

restart_service_if_any() {
  if service_installed; then
    info "Restarting ${SERVICE_NAME}..."
    sudo_wrap systemctl restart "$SERVICE_NAME"
    ok "Service restarted"
  else
    warn "systemd service not installed. Start manually:"
    echo -e "    ${C}source .venv/bin/activate && python run.py${N}"
  fi
}

# ── actions ─────────────────────────────────────────────
cmd_install() {
  banner_small "Install"
  require_ubuntu_22_plus || return 1
  ensure_apt_packages || return 1
  ensure_python || return 1

  # Defaults — all bot/admin/PasarGuard config is done in the web wizard (/setup)
  WEB_PORT="${WEB_PORT:-9000}"
  WEB_SECRET="$(gen_secret)"
  BOT_TOKEN=""
  BOT_USERNAME=""
  ADMIN_IDS=""
  PG_BASE_URL=""
  PG_USERNAME=""
  PG_PASSWORD=""
  WEB_ADMIN_USER="admin"
  WEB_ADMIN_PASSWORD=""
  PUBLIC_BASE_URL=""
  CURRENCY="تومان"

  local fresh=0
  if [[ -f .env ]]; then
    warn ".env already exists — keeping it (no overwrite)."
    WEB_PORT="$(env_get WEB_PORT "${WEB_PORT}")"
    ok "Using existing config · port=${WEB_PORT}"
  else
    fresh=1
  fi

  step "Python packages"
  ensure_venv || return 1
  mkdir -p data

  if [[ "$fresh" -eq 1 ]]; then
    step "Scaffold configuration"
    write_env_file
    rm -f data/web_admin.json data/setup_complete.flag data/setup_in_progress.flag 2>/dev/null || true
    ok ".env scaffold written · finish setup in the browser"
  fi

  step "systemd service"
  install_systemd "$(whoami)" || true
  if service_installed; then
    sudo_wrap systemctl enable --now "$SERVICE_NAME" || true
    if service_active; then
      ok "Service is running"
    else
      warn "Service installed but not active — check: journalctl -u ${SERVICE_NAME} -n 50"
    fi
  else
    warn "systemd unit missing — starting panel in background"
    nohup "${SCRIPT_DIR}/.venv/bin/python" "${SCRIPT_DIR}/run.py" \
      >/tmp/pgclock-panel.log 2>&1 &
    ok "Panel started (pid $!) · log: /tmp/pgclock-panel.log"
  fi

  step "Firewall"
  if command -v ufw >/dev/null 2>&1; then
    sudo_wrap ufw allow "${WEB_PORT}/tcp" >/dev/null 2>&1 || true
    ok "UFW: allowed ${WEB_PORT}/tcp (if UFW is active)"
  else
    info "UFW not installed — open port ${WEB_PORT} manually if needed"
  fi

  local ip panel_url
  ip="$(detect_server_ip)"
  panel_url="http://${ip}:${WEB_PORT}/"

  if [[ "$fresh" -eq 1 ]] || [[ ! -f data/setup_complete.flag ]]; then
    print_success "Install complete — open the web panel" \
      "Panel:      ${panel_url}" \
      "First open: setup wizard · later: login" \
      "Manage:     bash pgclock.sh" \
      "Logs:       journalctl -u ${SERVICE_NAME} -f"
  else
    print_success "Install/refresh complete" \
      "Panel:      ${panel_url}" \
      "Manage:     bash pgclock.sh" \
      "Logs:       journalctl -u ${SERVICE_NAME} -f"
  fi
  return 0
}

cmd_update() {
  banner_small "Update"
  if [[ ! -f .env ]]; then
    err ".env not found. Run Install first."
    return 1
  fi
  ok "Keeping existing .env"
  cp -a .env ".env.bak.$(date +%Y%m%d%H%M%S)"
  ok ".env backup created"

  if [[ -d .git ]]; then
    info "Pulling latest code from GitHub..."
    local branch
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
    if [[ "$branch" == "HEAD" ]]; then
      branch="main"
    fi
    # Targeted fetch (no tags / no --all) — much faster on weak VPS links
    if ! timeout 120 git fetch --no-tags --prune origin "$branch" 2>/dev/null; then
      timeout 120 git fetch --no-tags --prune origin main || true
      branch="main"
    fi
    if git pull --ff-only origin "$branch" 2>/dev/null || git pull --ff-only 2>/dev/null; then
      ok "Code updated (branch: ${branch})"
    else
      warn "Fast-forward failed — syncing hard to origin/main (keeps .env + data)"
      git fetch --no-tags --prune origin main || true
      git checkout -f -B main origin/main
      git reset --hard origin/main
      git clean -fd --exclude=.env --exclude=data --exclude=.venv --exclude='.env.bak.*'
      ok "Code synced to origin/main"
    fi
  else
    warn "Not a git repo — skipped git pull."
  fi

  ensure_python || return 1
  ensure_venv || return 1
  mkdir -p data
  "$PY" - <<'PY' || true
from app.services.web_auth import AUTH_FILE, load_web_admin
creds = load_web_admin()
print(f"web_admin={creds.get('username')} file={AUTH_FILE.exists()}")
PY

  if [[ ! -f .env ]]; then
    local latest_bak
    latest_bak="$(ls -1t .env.bak.* 2>/dev/null | head -n1 || true)"
    if [[ -n "$latest_bak" ]]; then
      cp -a "$latest_bak" .env
      warn "Restored .env from backup"
    else
      err ".env missing after update."
      return 1
    fi
  fi

  restart_service_if_any
  print_success "Update complete" \
    "Config:     .env was not changed" \
    "Logs:       journalctl -u ${SERVICE_NAME} -f"
  return 0
}

cmd_edit_env() {
  banner_small "Edit .env"
  if [[ ! -f .env ]]; then
    if [[ -f .env.example ]]; then
      cp .env.example .env
      warn "Created .env from .env.example — fill in values."
    else
      err ".env not found. Run Install first."
      return 1
    fi
  fi
  cp -a .env ".env.bak.$(date +%Y%m%d%H%M%S)"
  ok "Backup created"
  local editor="${EDITOR:-nano}"
  if ! command -v "$editor" >/dev/null 2>&1; then
    editor="nano"
  fi
  if ! command -v "$editor" >/dev/null 2>&1; then
    editor="vi"
  fi
  info "Opening with ${editor}..."
  "$editor" .env
  echo ""
  if ask_yn "Restart service to apply changes?" "Y"; then
    restart_service_if_any
  fi
  print_success "Configuration saved" \
    "Edited:     .env"
  return 0
}

cmd_web_panel() {
  while true; do
    banner_small "Web panel"
    local port user ip
    port="$(env_get WEB_PORT 9000)"
    user="$(web_username)"
    ip="$(detect_server_ip)"
    echo -e "  Login URL : ${B}http://${ip}:${port}/login${N}"
    echo -e "  Health    : ${B}http://127.0.0.1:${port}/health${N}"
    echo -e "  Username  : ${B}${user}${N}"
    echo ""
    echo -e "  ${B}1)${N} Reset web password"
    echo -e "  ${B}2)${N} Check /health"
    echo -e "  ${B}3)${N} Allow firewall port ${port}/tcp"
    echo -e "  ${B}0)${N} Back"
    echo ""
    local choice=""
    prompt_read choice "  ${B}Select${N}: "
    case "${choice}" in
      1)
        if [[ ! -f .venv/bin/python ]]; then
          err "venv missing. Run Install first."
        else
          "$PY" scripts/set_web_password.py
          restart_service_if_any
          print_success "Web password updated"
        fi
        pause
        ;;
      2)
        if command -v curl >/dev/null 2>&1; then
          echo ""
          curl -sS "http://127.0.0.1:${port}/health" || err "Health check failed (is the bot running?)"
          echo ""
          echo ""
          ok "Health check finished"
        else
          err "curl not installed."
        fi
        pause
        ;;
      3)
        if command -v ufw >/dev/null 2>&1; then
          sudo_wrap ufw allow "${port}/tcp" >/dev/null 2>&1 || true
          ok "UFW allowed ${port}/tcp"
        else
          echo -e "  Run manually: ${C}sudo ufw allow ${port}/tcp && sudo ufw reload${N}"
        fi
        pause
        ;;
      0) return 0 ;;
      "") ;;
      *) err "Invalid option." ; pause ;;
    esac
  done
}

cmd_service() {
  while true; do
    banner_small "Service"
    if service_installed; then
      local state
      state="$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo unknown)"
      echo -e "  Unit  : ${B}${SERVICE_NAME}${N}"
      echo -e "  State : ${B}${state}${N}"
    else
      echo -e "  ${D}systemd unit not installed${N}"
    fi
    echo ""
    echo -e "  ${B}1)${N} Status"
    echo -e "  ${B}2)${N} Start / Enable"
    echo -e "  ${B}3)${N} Restart"
    echo -e "  ${B}4)${N} Stop"
    echo -e "  ${B}5)${N} Logs (follow, Ctrl+C to stop)"
    echo -e "  ${B}6)${N} Install systemd unit"
    echo -e "  ${B}0)${N} Back"
    echo ""
    local choice=""
    prompt_read choice "  ${B}Select${N}: "
    case "${choice}" in
      1)
        if service_installed; then
          systemctl status "$SERVICE_NAME" --no-pager || true
          ok "Status shown"
        else
          warn "Service not installed."
        fi
        pause
        ;;
      2)
        if ! service_installed; then
          install_systemd "$(whoami)"
        else
          sudo_wrap systemctl enable --now "$SERVICE_NAME"
          ok "Started"
        fi
        print_success "Service start requested"
        pause
        ;;
      3)
        restart_service_if_any
        print_success "Service restart requested"
        pause
        ;;
      4)
        if service_installed; then
          sudo_wrap systemctl stop "$SERVICE_NAME"
          ok "Stopped"
        else
          warn "Service not installed."
        fi
        pause
        ;;
      5)
        if service_installed; then
          journalctl -u "$SERVICE_NAME" -f
        else
          warn "Service not installed."
          pause
        fi
        ;;
      6)
        if [[ ! -d .venv ]]; then
          err "Run Install first."
        else
          install_systemd "$(ask "System user" "$(whoami)")"
          print_success "systemd unit installed"
        fi
        pause
        ;;
      0) return 0 ;;
      "") ;;
      *) err "Invalid option." ; pause ;;
    esac
  done
}

cmd_uninstall() {
  banner_small "Uninstall"
  warn "FULL uninstall removes EVERYTHING for this bot:"
  warn "  systemd service, running processes, .venv, data, .env, backups,"
  warn "  and the entire project folder: ${SCRIPT_DIR}"
  if ! ask_yn "Continue full uninstall?" "N"; then
    info "Cancelled."
    return 0
  fi

  # Stop & remove systemd
  if service_installed || [[ -f "$SERVICE_PATH" ]]; then
    info "Stopping systemd service..."
    sudo_wrap systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
    sudo_wrap rm -f "$SERVICE_PATH"
    sudo_wrap systemctl daemon-reload 2>/dev/null || true
    ok "systemd unit removed"
  else
    info "No systemd unit found."
  fi

  # Kill leftover bot processes from this install
  info "Stopping leftover processes..."
  pkill -f "${SCRIPT_DIR}/.venv/bin/python .*run.py" 2>/dev/null || true
  pkill -f "python .*${SCRIPT_DIR}/run.py" 2>/dev/null || true
  # free web port if still held
  local port
  port="$(env_get WEB_PORT 9000)"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi

  local root="$SCRIPT_DIR"
  info "Deleting project folder: ${root}"
  cd / || cd "$HOME" || true
  rm -rf "$root"

  printf '\n' > /dev/tty
  printf '%s==========================================%s\n' "$G" "$N" > /dev/tty
  printf '%s  SUCCESS · Full uninstall complete%s\n' "$G" "$N" > /dev/tty
  printf '%s==========================================%s\n' "$G" "$N" > /dev/tty
  printf '  Removed: %s\n' "$root" > /dev/tty
  printf '  Reinstall:\n' > /dev/tty
  printf '    bash <(curl -fsSL https://raw.githubusercontent.com/Mrclocks/PGClockBot/main/get.sh)\n' > /dev/tty
  printf '%s==========================================%s\n\n' "$G" "$N" > /dev/tty
  exit 0
}

cmd_status() {
  banner_small "Status"
  if [[ -f .env ]]; then
    ok ".env present"
  else
    warn ".env missing"
  fi
  if [[ -d .venv ]]; then
    ok "venv present"
  else
    warn "venv missing"
  fi
  local port
  port="$(env_get WEB_PORT 9000)"
  if service_installed; then
    echo -e "  Service: ${B}$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo unknown)${N}"
  else
    echo -e "  Service: ${D}not installed${N}"
  fi
  if command -v curl >/dev/null 2>&1; then
    local health
    health="$(curl -sS --max-time 3 "http://127.0.0.1:${port}/health" 2>/dev/null || true)"
    if [[ -n "$health" ]]; then
      ok "Web health: ${health}"
    else
      warn "Web health: unreachable on :${port}"
    fi
  fi
  print_success "Status check"
  return 0
}

cmd_help() {
  cat <<EOF

  PGClockBot manager

  Usage:
    bash pgclock.sh                 Interactive menu
    bash pgclock.sh install         Silent install (config via /setup wizard)
    bash pgclock.sh update          Update code + deps
    bash pgclock.sh env             Edit .env
    bash pgclock.sh web             Web panel tools
    bash pgclock.sh service         systemd controls
    bash pgclock.sh status          Quick status
    bash pgclock.sh uninstall       Remove service / data
    bash pgclock.sh help            This help

  One-liner (clone OR update existing folder, then menu):
    bash <(curl -fsSL https://raw.githubusercontent.com/Mrclocks/PGClockBot/main/get.sh)

  Inside the project:
    bash get.sh
    bash pgclock.sh

EOF
}

# ── UI ──────────────────────────────────────────────────
banner() {
  {
    printf '%s\n' "$C"
    cat <<'ART'
   ==========================================
            P G C l o c k B o t
        PasarGuard Telegram Shop CLI
   ==========================================
ART
    printf '%s\n' "$N"
    printf '  %sUbuntu 22.04+  ·  English  ·  One command for everything%s\n' "$D" "$N"
    echo ""
  } > /dev/tty
}

banner_small() {
  {
    echo ""
    printf '%s==========================================%s\n' "$C" "$N"
    printf '%s  PGClockBot · %s%s\n' "$B" "$*" "$N"
    printf '%s==========================================%s\n' "$C" "$N"
    echo ""
  } > /dev/tty
}

show_menu() {
  clear > /dev/tty 2>/dev/null || printf '\033c' > /dev/tty
  banner
  {
    printf '  %s1)%s Install        Silent install → finish in /setup wizard\n' "$B" "$N"
    printf '  %s2)%s Update         Pull latest code (keep .env)\n' "$B" "$N"
    printf '  %s3)%s Edit .env      Change tokens / panel / ports\n' "$B" "$N"
    printf '  %s4)%s Web panel      URL, password reset, health\n' "$B" "$N"
    printf '  %s5)%s Service        Status / restart / logs\n' "$B" "$N"
    printf '  %s6)%s Status         Quick health overview\n' "$B" "$N"
    printf '  %s7)%s Uninstall      Remove EVERYTHING (full wipe)\n' "$B" "$N"
    printf '  %s0)%s Exit\n' "$B" "$N"
    echo ""
  } > /dev/tty
}

run_menu() {
  while true; do
    show_menu
    local choice=""
    prompt_read choice "  ${B}Select option${N}: "
    case "${choice}" in
      1|install|i) cmd_install ; pause ;;
      2|update|u)  cmd_update  ; pause ;;
      3|env|edit)  cmd_edit_env ; pause ;;
      4|web)       cmd_web_panel ;;
      5|service)   cmd_service ;;
      6|status)    cmd_status ; pause ;;
      7|uninstall) cmd_uninstall ; pause ;;
      0|exit|q|quit)
        echo ""
        ok "Bye."
        exit 0
        ;;
      "")
        ;;
      *)
        err "Invalid option."
        pause
        ;;
    esac
  done
}

dispatch() {
  local cmd="${1:-}"
  case "${cmd}" in
    ""|menu)       run_menu ;;
    install|i)     cmd_install ;;
    update|u)      cmd_update ;;
    env|edit|edit-env|dotenv) cmd_edit_env ;;
    web|panel|web-panel) cmd_web_panel ;;
    service|svc)   cmd_service ;;
    status|s)      cmd_status ;;
    uninstall|remove) cmd_uninstall ;;
    help|-h|--help) cmd_help ;;
    *)
      err "Unknown command: ${cmd}"
      cmd_help
      exit 1
      ;;
  esac
}

dispatch "${1:-}"
