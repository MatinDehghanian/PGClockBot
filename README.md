# PGClockBot

Telegram shop bot for **PasarGuard** — Persian bot UI, English management CLI, web panel on port `9000`.

---

## One-line manager (Ubuntu 22.04+)

```bash
git clone https://github.com/Mrclocks/PGClockBot.git && cd PGClockBot && bash pgclock.sh
```

Or after clone:

```bash
bash pgclock.sh
```

Menu:

| # | Action | What it does |
|---|--------|----------------|
| 1 | **Install** | Fresh setup (Telegram + PasarGuard + web login + systemd) |
| 2 | **Update** | `git pull` + deps — keeps `.env` |
| 3 | **Edit .env** | Open config in nano/vi, optional restart |
| 4 | **Web panel** | Show URL, reset password, `/health` check |
| 5 | **Service** | Status / start / restart / stop / logs |
| 6 | **Status** | Quick overview |
| 7 | **Uninstall** | Remove systemd (+ optional wipe data) |
| 0 | **Exit** | Quit |

Direct commands (no menu):

```bash
bash pgclock.sh install
bash pgclock.sh update
bash pgclock.sh env
bash pgclock.sh web
bash pgclock.sh service
bash pgclock.sh status
bash pgclock.sh uninstall
bash pgclock.sh help
```

Legacy wrappers still work: `./install.sh` → install, `./update.sh` → update.

---

## Features

- Guest purchase (plans, wallet, card-to-card)
- My services, renew, support, expiry / traffic alerts
- Reseller role (commission, receipt approve)
- Admin tools in bot + PasarGuard ops
- Web admin panel on `:9000`
- Optional Telegram Mini App (HTTPS URL)

---

## Requirements

| Item | Notes |
|------|--------|
| OS | **Ubuntu 22.04+** |
| PasarGuard panel | Reachable API |
| Telegram bot | Token from [@BotFather](https://t.me/BotFather) |
| Admin Telegram ID | Numeric ID from [@userinfobot](https://t.me/userinfobot) |

---

## Web panel

Open `http://SERVER_IP:9000/login` with the username/password from Install.

Configure texts, buttons, card number, and plans from **Settings**.

### Login / health issues

```bash
bash pgclock.sh web
# or:
curl http://127.0.0.1:9000/health
bash pgclock.sh   # → Web panel → Reset password
sudo ufw allow 9000/tcp
```

Credentials live in `data/web_admin.json` (not only `.env`).

---

## Bot not answering /start

```bash
bash pgclock.sh service   # → Logs
# or:
journalctl -u pgclockbot -f
```

Expect: `Bot online as @YourBot …`  
Ensure only one bot process is running. Check `ADMIN_IDS` is your numeric ID.

---

## Manual install (without menu)

```bash
git clone https://github.com/Mrclocks/PGClockBot.git
cd PGClockBot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python run.py
```

Quote secrets with special characters:

```env
WEB_ADMIN_PASSWORD="MyPass!A"
PG_PASSWORD="Secret#1"
```

---

## Mini App (optional)

HTTPS reverse proxy → port `9000`, then in `.env`:

```env
PUBLIC_BASE_URL="https://bot.example.com"
```

Or set it during Install (Enter to skip).

---

## Security

- Do not commit `.env` or `data/`
- Use a strong web password and `WEB_SECRET`
- Prefer Nginx + HTTPS in production
