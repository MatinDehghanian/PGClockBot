#!/usr/bin/env bash
# PGClockBot — Update without re-entering configuration
set -euo pipefail
set +H

R='\033[0;31m'; G='\033[0;32m'; C='\033[0;36m'
Y='\033[1;33m'; B='\033[1;37m'; D='\033[2m'; N='\033[0m'

info()  { echo -e "  ${C}›${N} $*"; }
ok()    { echo -e "  ${G}✔${N} $*"; }
warn()  { echo -e "  ${Y}!${N} $*"; }
err()   { echo -e "  ${R}✖${N} $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo -e "${C}╔══════════════════════════════════════════╗${N}"
echo -e "${C}║       PGClockBot — Update                ║${N}"
echo -e "${C}╚══════════════════════════════════════════╝${N}"
echo ""

if [[ ! -f .env ]]; then
  err ".env not found. Run ./install.sh first."
  exit 1
fi
ok "Keeping existing .env (settings preserved)"

# Backup .env before pull
cp -a .env ".env.bak.$(date +%Y%m%d%H%M%S)"
ok ".env backup created"

if [[ -d .git ]]; then
  info "Fetching latest code from GitHub..."
  # stash local tracked changes except .env (already ignored)
  git fetch --all --tags
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  git pull --ff-only origin "$BRANCH" || git pull --ff-only
  ok "Code updated (branch: $BRANCH)"
else
  warn "Not a git repo — skipped git pull. Copy new files manually then re-run."
fi

if [[ ! -d .venv ]]; then
  info "Creating venv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
info "Installing/updating Python packages..."
pip install -U pip wheel -q
pip install -r requirements.txt -q
ok "Dependencies up to date"

# Ensure .env still present after pull
if [[ ! -f .env ]]; then
  LATEST_BAK="$(ls -1t .env.bak.* 2>/dev/null | head -n1 || true)"
  if [[ -n "$LATEST_BAK" ]]; then
    cp -a "$LATEST_BAK" .env
    warn "Restored .env from backup"
  else
    err ".env missing after update."
    exit 1
  fi
fi

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q '^pgclockbot.service'; then
  info "Restarting systemd service..."
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl restart pgclockbot
  else
    sudo systemctl restart pgclockbot
  fi
  ok "Service restarted"
  echo ""
  echo -e "  Logs: ${B}journalctl -u pgclockbot -f${N}"
else
  echo ""
  warn "systemd service not found. Start manually:"
  echo -e "  ${B}source .venv/bin/activate && python run.py${N}"
fi

echo ""
ok "Update complete — bot config (.env) was not changed."
echo ""
echo -e "  Optional: reset web login without reinstall:"
echo -e "  ${B}python scripts/set_web_password.py${N}"
echo ""
