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
REMOTE_BRANCH="${PGCLOCK_BRANCH:-main}"

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

backup_runtime() {
  # Preserve config + DB outside of git reset
  RUNTIME_BAK="$(mktemp -d /tmp/pgclock-runtime.XXXXXX)"
  mkdir -p "$RUNTIME_BAK"
  for item in .env data .venv; do
    if [[ -e "$item" ]]; then
      cp -a "$item" "$RUNTIME_BAK/" 2>/dev/null || true
    fi
  done
  # Keep recent .env backups too
  shopt -s nullglob
  local bak
  for bak in .env.bak.*; do
    cp -a "$bak" "$RUNTIME_BAK/" 2>/dev/null || true
  done
  shopt -u nullglob
  ok "Runtime backup → ${RUNTIME_BAK}"
}

restore_runtime() {
  local bak_dir="${1:-}"
  [[ -n "$bak_dir" && -d "$bak_dir" ]] || return 0
  if [[ -e "${bak_dir}/.env" && ! -e .env ]]; then
    cp -a "${bak_dir}/.env" .env
    ok "Restored .env"
  elif [[ -e "${bak_dir}/.env" && -e .env ]]; then
    # Prefer existing .env in tree; keep backup copy nearby
    cp -a "${bak_dir}/.env" ".env.restored.from.backup" 2>/dev/null || true
  fi
  if [[ -d "${bak_dir}/data" ]]; then
    mkdir -p data
    cp -a "${bak_dir}/data/." data/ 2>/dev/null || true
    ok "Restored data/"
  fi
  shopt -s nullglob
  local bak
  for bak in "${bak_dir}"/.env.bak.*; do
    cp -a "$bak" . 2>/dev/null || true
  done
  shopt -u nullglob
}

force_sync_to_remote() {
  info "Syncing hard to origin/${REMOTE_BRANCH} (keeps .env + data)..."
  backup_runtime
  local bak="$RUNTIME_BAK"

  git remote set-url origin "$REPO_URL" 2>/dev/null || git remote add origin "$REPO_URL" 2>/dev/null || true
  git fetch --all --tags

  # Detach local dirty state safely
  git checkout -f -B "$REMOTE_BRANCH" "origin/${REMOTE_BRANCH}"
  git reset --hard "origin/${REMOTE_BRANCH}"
  git clean -fd --exclude=.env --exclude=data --exclude=.venv --exclude='.env.bak.*' --exclude='.env.restored.*'

  restore_runtime "$bak"
  ok "Code synced to origin/${REMOTE_BRANCH}"
}

git_update() {
  if [[ ! -d .git ]]; then
    warn "Not a git repo — skipping pull"
    return 0
  fi

  info "Updating from GitHub..."
  git remote set-url origin "$REPO_URL" 2>/dev/null || true
  git fetch --all --tags 2>/dev/null || true

  local branch
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "$REMOTE_BRANCH")"
  if [[ "$branch" == "HEAD" ]]; then
    branch="$REMOTE_BRANCH"
  fi

  if git pull --ff-only "origin" "$branch" 2>/dev/null \
    || git pull --ff-only 2>/dev/null; then
    ok "Code updated (branch: ${branch})"
    return 0
  fi

  warn "Fast-forward failed (local changes or divergent history)."
  force_sync_to_remote
}

ensure_repo() {
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
      warn "Folder exists without .git — re-cloning into place"
      backup_runtime
      local bak="$RUNTIME_BAK"
      cd ..
      rm -rf "$ROOT"
      git clone "$REPO_URL" "$ROOT"
      cd "$ROOT"
      restore_runtime "$bak"
      ok "Re-cloned and restored runtime files"
    fi
    return 0
  fi

  info "Cloning ${REPO_URL} → ${ROOT}"
  git clone "$REPO_URL" "$ROOT"
  cd "$ROOT"
  ok "Clone complete"
}

ensure_repo

# Final safety: if manager still missing, force sync once more
if [[ ! -f pgclock.sh ]]; then
  warn "pgclock.sh missing after update — forcing sync to origin/${REMOTE_BRANCH}"
  if [[ -d .git ]]; then
    force_sync_to_remote
  fi
fi

if [[ ! -f pgclock.sh ]]; then
  err "pgclock.sh still missing in ${ROOT}"
  err "Manual fix:"
  err "  cd ~ && mv ${DIR_NAME} ${DIR_NAME}.bak.\$(date +%Y%m%d)"
  err "  curl -fsSL https://raw.githubusercontent.com/Mrclocks/PGClockBot/main/get.sh | bash"
  exit 1
fi

chmod +x pgclock.sh get.sh install.sh update.sh 2>/dev/null || true

# Pass through optional subcommand (install/update/...), default = menu
exec bash pgclock.sh "$@"
