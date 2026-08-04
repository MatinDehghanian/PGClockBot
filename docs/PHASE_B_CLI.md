# Phase B — Global CLI (`pgclock`)

**Scope:** Global operations CLI only. Database behavior unchanged from Phase A.  
**Out of scope:** permissions, identity sync, PasarGuard admin logic, node management.

---

## Installation

From the project root (requires sudo once):

```bash
sudo bash scripts/install_global_cli.sh
# or explicitly:
sudo bash scripts/install_global_cli.sh /path/to/PGClockBot
```

This writes:

| Path | Purpose |
|------|---------|
| `/usr/local/bin/pgclock` | Global command |
| `/usr/local/lib/pgclockbot/install_root` | Absolute install path |
| `/usr/local/lib/pgclockbot/ctl` | (via install helper) constrained systemctl verbs |

`bash pgclock.sh install` / systemd install also refreshes the global CLI.

Without sudo, from the repo:

```bash
export PGCLOCK_HOME=/path/to/PGClockBot
./scripts/pgclock status
# or
.venv/bin/python -m app.cli status
```

---

## Commands

```bash
pgclock status
pgclock start
pgclock stop
pgclock restart
pgclock logs              # last 100 lines
pgclock logs -f           # follow
pgclock logs -n 200
pgclock health
pgclock backup [--note TEXT] [--no-env]
pgclock backup --list
pgclock restore <backup_id> [--yes] [--env] [--no-restart]
pgclock migrate                    # alembic upgrade head
pgclock migrate --from-sqlite --source 'sqlite+aiosqlite:///…' --target 'postgresql+asyncpg://…' -y
pgclock doctor
```

Optional: `pgclock --root /path/to/install status`

---

## Examples

```bash
pgclock doctor
pgclock status
pgclock backup --note "pre-update"
pgclock restore 20260804-120030-4745d007 --yes --no-restart
pgclock migrate
pgclock restart
pgclock health
```

---

## Tests

```bash
.venv/bin/python -m pytest tests/test_phase_b_cli.py -q
```

---

## Rollback

```bash
sudo rm -f /usr/local/bin/pgclock \
  /usr/local/lib/pgclockbot/install_root \
  /usr/local/lib/pgclockbot/pgclock-wrapper
# Optional: keep ctl/sudoers if panel restart helper is still needed.
```

Interactive `bash pgclock.sh` continues to work without the global binary.
