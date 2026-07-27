#!/usr/bin/env bash
# PGClockBot bootstrap — clone if missing, update if present, then open the menu.
#
# Fresh or existing server (from any directory):
#   curl -fsSL https://raw.githubusercontent.com/Mrclocks/PGClockBot/main/get.sh | bash
#
# Or locally (inside / next to the repo):
#   bash get.sh
#   bash get.sh update
#
set -euo pipefail

REPO_URL="${PGCLOCK_REPO:-https://github.com/Mrclocks/PGClockBot.git}"
DIR_NAME="${PGCLOCK_DIR:-PGClockBot}"

info() { echo "  > $*"; }
ok()   { echo "  + $*"; }
warn() { echo "  ! $*"; }
err()  { echo "  x $*" >&2; }

# Resolve project root
if [[ -f "./pgclock.sh" || -f "./install.sh" || -f "./run.py" ]]; then
  ROOT="$(pwd)"
else
  ROOT="$(pwd)/${DIR_NAME}"
fi

git_update() {
  if [[ ! -d .git ]]; then
    warn "Not a git repo — skipping pull"
    return 0
  fi
  info "Updating from GitHub..."
  git fetch --all --tags 2>/dev/null || true
  local branch
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
  if git pull --ff-only origin "$branch" 2>/dev/null \
    || git pull --ff-only 2>/dev/null; then
    ok "Code updated (branch: ${branch})"
  else
    warn "git pull could not fast-forward"
    warn "Try: cd ${ROOT} && git status"
    warn "Or backup & reinstall:"
    warn "  mv ${ROOT} ${ROOT}.bak.\$(date +%Y%m%d) && curl -fsSL https://raw.githubusercontent.com/Mrclocks/PGClockBot/main/get.sh | bash"
  fi
}

ensure_repo() {
  # Case A: already inside project (or ROOT points to existing checkout)
  if [[ -d "$ROOT" ]]; then
    cd "$ROOT"
    ok "Found existing folder: ${ROOT}"

    if [[ -d .git ]]; then
      git_update
    elif [[ ! -f pgclock.sh && ! -f run.py ]]; then
      err "Folder exists but is empty/incomplete and has no .git: ${ROOT}"
      err "Remove or rename it, then re-run:"
      err "  mv ${DIR_NAME} ${DIR_NAME}.bak.\$(date +%Y%m%d)"
      err "  curl -fsSL https://raw.githubusercontent.com/Mrclocks/PGClockBot/main/get.sh | bash"
      exit 1
    else
      warn "Folder exists without .git — using local files as-is"
    fi
    return 0
  fi

  # Case B: fresh clone
  info "Cloning ${REPO_URL} → ${ROOT}"
  git clone "$REPO_URL" "$ROOT"
  cd "$ROOT"
  ok "Clone complete"
}

ensure_repo

if [[ ! -f pgclock.sh ]]; then
  err "pgclock.sh still missing in ${ROOT}"
  err "Your copy may be too old or broken. Backup and re-clone:"
  err "  cd .. && mv ${DIR_NAME} ${DIR_NAME}.bak.\$(date +%Y%m%d)"
  err "  curl -fsSL https://raw.githubusercontent.com/Mrclocks/PGClockBot/main/get.sh | bash"
  exit 1
fi

chmod +x pgclock.sh get.sh install.sh update.sh 2>/dev/null || true

# Pass through optional subcommand (install/update/...), default = menu
exec bash pgclock.sh "$@"
