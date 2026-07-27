#!/usr/bin/env bash
# PGClockBot — Easy interactive installer
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
echo "========================================"
echo "   PGClockBot — نصب آسان"
echo "========================================"
echo ""

# ---- helpers ----
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
      err "این فیلد الزامی است."
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
    err "این فیلد الزامی است."
  done
}

# حداقل ۸ کاراکتر، یک حرف بزرگ، یک کاراکتر خاص
validate_password() {
  local p="$1"
  if [[ ${#p} -lt 8 ]]; then
    err "پسورد باید حداقل ۸ کاراکتر باشد."
    return 1
  fi
  if ! [[ "$p" =~ [A-Z] ]]; then
    err "پسورد باید حداقل یک حرف بزرگ انگلیسی (A-Z) داشته باشد."
    return 1
  fi
  if ! [[ "$p" =~ [^a-zA-Z0-9] ]]; then
    err "پسورد باید حداقل یک کاراکتر خاص داشته باشد (مثل ! @ # \$ % & *)."
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
    p2="$(ask_secret "تکرار پسورد")"
    if [[ "$p1" != "$p2" ]]; then
      err "پسوردها یکسان نیستند."
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

# ---- step 0: python ----
info "بررسی پیش‌نیازها..."
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  err "Python پیدا نشد. Python 3.10+ نصب کنید."
  exit 1
fi

PY_VER="$($PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
ok "Python $PY_VER"

# ---- interactive config ----
echo ""
info "مرحله ۱ — تلگرام"
BOT_TOKEN="$(ask "توکن ربات (از BotFather)")"
BOT_USERNAME="$(ask "یوزرنیم ربات بدون @" "PGClockBot")"
ADMIN_IDS="$(ask "آیدی عددی ادمین(ها) — چندتایی با ویرگول")"

echo ""
info "مرحله ۲ — اتصال پاسارگارد"
PG_BASE_URL="$(ask "آدرس پنل پاسارگارد" "https://dev.mrclock.website")"
PG_BASE_URL="${PG_BASE_URL%/}"
PG_USERNAME="$(ask "یوزرنیم ادمین پاسارگارد")"
PG_PASSWORD="$(ask_secret "رمز عبور ادمین پاسارگارد")"

echo ""
info "مرحله ۳ — وب‌پنل مدیریت (پورت ۹۰۰۰)"
WEB_PORT="$(ask "پورت وب‌پنل" "9000")"
WEB_ADMIN_USER="$(ask "نام کاربری ورود وب‌پنل" "admin")"
echo "قوانین پسورد وب‌پنل: حداقل ۸ کاراکتر + یک حرف بزرگ + یک کاراکتر خاص"
WEB_ADMIN_PASSWORD="$(ask_password "پسورد وب‌پنل")"
WEB_SECRET="$(gen_secret)"

echo ""
info "مرحله ۴ — تنظیمات اختیاری (Enter = رد کردن)"
PUBLIC_BASE_URL="$(ask "آدرس HTTPS عمومی برای مینی‌اپ (خالی بگذارید اگر ندارید)" "")"
CURRENCY="$(ask "واحد پول" "تومان")"

echo ""
info "مرحله ۵ — نصب وابستگی‌ها"
if [[ ! -d .venv ]]; then
  $PY -m venv .venv
  ok "محیط مجازی ساخته شد"
else
  ok "محیط مجازی از قبل موجود است"
fi

# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip wheel >/dev/null
pip install -r requirements.txt
ok "پکیج‌ها نصب شدند"

echo ""
info "مرحله ۶ — نوشتن فایل .env"
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
ok "فایل .env ذخیره شد (دسترسی محدود)"

mkdir -p data
ok "پوشه data آماده است"

echo ""
info "مرحله ۷ — سرویس systemd (اختیاری)"
INSTALL_SERVICE="$(ask "سرویس دائمی systemd ساخته شود؟ (y/N)" "N")"
if [[ "${INSTALL_SERVICE,,}" == "y" || "${INSTALL_SERVICE,,}" == "yes" ]]; then
  SERVICE_USER="$(ask "یوزر سیستم برای اجرا" "$(whoami)")"
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
    ok "سرویس pgclockbot فعال شد"
  else
    TMP_SVC="$(mktemp)"
    echo "$SERVICE_CONTENT" > "$TMP_SVC"
    warn "برای ساخت سرویس به sudo نیاز است:"
    echo "  sudo cp $TMP_SVC $SERVICE_PATH"
    echo "  sudo systemctl daemon-reload && sudo systemctl enable --now pgclockbot"
  fi
fi

echo ""
echo "========================================"
ok "نصب تمام شد"
echo "========================================"
echo ""
echo "ورود وب‌پنل:"
echo "  آدرس:   http://SERVER_IP:${WEB_PORT}"
echo "  کاربر:  ${WEB_ADMIN_USER}"
echo "  (پسورد همانی که وارد کردید)"
echo ""
echo "از وب‌پنل می‌توانید متن‌ها، دکمه‌ها، کارت بانکی، پلن‌ها و بقیه تنظیمات را تغییر دهید."
echo ""
echo "اجرای دستی:"
echo "  source .venv/bin/activate"
echo "  python run.py"
echo ""

START_NOW="$(ask "الان ربات را اجرا کنم؟ (Y/n)" "Y")"
if [[ "${START_NOW,,}" != "n" && "${START_NOW,,}" != "no" ]]; then
  if systemctl is-active --quiet pgclockbot 2>/dev/null; then
    ok "سرویس systemd در حال اجراست — journalctl -u pgclockbot -f"
  else
    info "در حال اجرا... (Ctrl+C برای توقف)"
    exec .venv/bin/python run.py
  fi
fi
