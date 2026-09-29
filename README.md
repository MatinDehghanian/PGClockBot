# PGClockBot

**v11.0.6** — Telegram shop bot for **PasarGuard**. Persian bot UI, English management CLI, web panel on port `9000`.

---

## Quick start (Ubuntu 22.04+)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Mrclocks/PGClockBot/main/get.sh)
```

Works on a fresh server or an existing `PGClockBot` folder (syncs to latest, then opens the menu).

Already inside the repo:

```bash
bash pgclock.sh
```

| # | Action | |
|---|--------|--|
| 1 | **Install** | Deps + systemd → open `/setup` in the browser |
| 2 | **Update** | `git pull` + deps (keeps `.env`) |
| 3 | **Edit .env** | Open config, optional restart |
| 4 | **Web panel** | URL, password reset, `/health` |
| 5 | **Service** | Status / start / restart / stop / logs |
| 6 | **Status** | Quick overview |
| 7 | **Uninstall** | Remove systemd (+ optional wipe) |

```bash
bash pgclock.sh install|update|env|web|service|status|uninstall|help
```

Legacy wrappers: `./install.sh` → install, `./update.sh` → update.

---

## Features

- Guest purchase (plans, wallet, card-to-card / gateway)
- My services, renew, support, expiry & traffic alerts
- Reseller role + PasarGuard ops
- Web admin on `:9000` with in-panel Persian help (`/help`)
- Optional Telegram Mini App (HTTPS)

---

## Requirements

| | |
|--|--|
| OS | Ubuntu 22.04+ |
| PasarGuard | Reachable API |
| Bot token | [@BotFather](https://t.me/BotFather) |
| Admin ID | Numeric ID from [@userinfobot](https://t.me/userinfobot) |

---

## Web panel

After install: `http://SERVER_IP:9000/`

- First visit → setup wizard  
- Later → login  

Persian docs: `http://SERVER_IP:9000/help/` (circular **؟** next to page titles).  
Optional public docs site: set `DOCS_BASE_URL` (see `docs/guide/README.md`).

```bash
bash pgclock.sh web
curl http://127.0.0.1:9000/health
sudo ufw allow 9000/tcp
```

Credentials live in `data/web_admin.json` (not only `.env`).

---

## Database

Fresh installs provision **PostgreSQL automatically** (packages, role, database, `.env`).
Optional override for managed/remote Postgres:

```bash
export PGCLOCK_DATABASE_URL="postgresql+asyncpg://user:SECRET@127.0.0.1:5432/pgclock"
bash pgclock.sh install
```

Manual provision (rare): `sudo bash scripts/setup_postgres.sh`  
Schema/migrations notes: `docs/PHASE_A_DATABASE.md`.

```bash
sudo bash scripts/install_global_cli.sh
pgclock status && pgclock doctor && pgclock backup
```

Full CLI: `docs/PHASE_B_CLI.md`.

---

## Mini App (optional)

HTTPS reverse proxy → `9000`, then:

```env
PUBLIC_BASE_URL="https://bot.example.com"
```

---

## Troubleshooting

**Bot ignores `/start`**

```bash
bash pgclock.sh service   # → Logs
journalctl -u pgclockbot -f
```

Expect `Bot online as @YourBot`. One bot process only; `ADMIN_IDS` must be numeric.

**Manual install**

```bash
git clone https://github.com/Mrclocks/PGClockBot.git && cd PGClockBot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && chmod 600 .env
python run.py   # finish secrets in the browser wizard
```

Quote secrets with special characters: `WEB_ADMIN_PASSWORD="MyPass!A"`.

---

## Security

- Do not commit `.env` or `data/`
- Use a strong web password and `WEB_SECRET`
- Prefer Nginx + HTTPS in production
