# PGClockBot

ربات فروش و مدیریت پنل **PasarGuard** — سبک، فارسی، با وب‌پنل روی پورت `9000` و مینی‌اپ تلگرام.

---

## امکانات

- خرید برای کاربر تازه‌وارد (پلن، کیف پول، کارت‌به‌کارت)
- سرویس من، تمدید، پشتیبانی، اعلان انقضا / اتمام حجم
- نقش **نماینده** (کمیسیون، تأیید رسید)
- پنل ادمین داخل بات + عملیات پاسارگارد (جستجو، ریست، disable، نودها، آمار)
- وب‌پنل مدیریت مینیمال روی `:9000`
- مینی‌اپ تلگرام (با دامنه HTTPS)

---

## پیش‌نیازها

| مورد | توضیح |
|------|--------|
| سرور / سیستم | Linux یا Windows با دسترسی اینترنت |
| Python | **3.10 تا 3.12** (پیشنهادی 3.11+) |
| پنل PasarGuard | API در دسترس (مثلاً `https://your-panel.com`) |
| بات تلگرام | توکن از [@BotFather](https://t.me/BotFather) |
| آیدی عددی ادمین | از [@userinfobot](https://t.me/userinfobot) |

---

## نصب مرحله‌ای (Ubuntu / Debian)

### ۱) کلون ریپو

```bash
git clone https://github.com/Mrclocks/PGClockBot.git
cd PGClockBot
```

### ۲) ساخت محیط مجازی و نصب پکیج‌ها

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

### ۳) ساخت فایل تنظیمات

```bash
cp .env.example .env
nano .env   # یا هر ادیتور دیگر
```

حداقل این مقادیر را پر کنید:

```env
BOT_TOKEN=123456:AA...your_token
BOT_USERNAME=YourBotUsername
ADMIN_IDS=123456789

PG_BASE_URL=https://dev.mrclock.website
PG_USERNAME=admin
PG_PASSWORD=your_panel_password

WEB_HOST=0.0.0.0
WEB_PORT=9000
WEB_SECRET=یک-رمز-بلند-تصادفی
WEB_ADMIN_USER=admin
WEB_ADMIN_PASSWORD=یک-رمز-قوی

DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
```

نکته‌ها:

- `ADMIN_IDS` را با ویرگول جدا کنید اگر چند ادمین دارید: `111,222`
- اگر توکن آماده پاسارگارد دارید، می‌توانید `PG_ACCESS_TOKEN=...` بگذارید و یوزر/پسورد را خالی بگذارید
- برای شروع، `WEBHOOK_URL` و `PUBLIC_BASE_URL` را خالی بگذارید (حالت polling)

### ۴) اجرای ربات

```bash
source .venv/bin/activate
python run.py
```

اگر درست باشد:

- ربات در تلگرام به `/start` جواب می‌دهد
- وب‌پنل روی `http://YOUR_SERVER_IP:9000` باز می‌شود

ورود وب‌پنل پیش‌فرض:

- کاربر: مقدار `WEB_ADMIN_USER`
- رمز: مقدار `WEB_ADMIN_PASSWORD`

### ۵) تست سریع در تلگرام

1. بات را باز کنید و `/start` بزنید
2. اگر آیدی شما در `ADMIN_IDS` باشد، دکمه **پنل ادمین** را می‌بینید
3. از وب‌پنل → **تنظیمات** شماره کارت را وارد کنید
4. از وب‌پنل → **پلن‌ها** یک پلن بسازید و `Template ID` پاسارگارد را بزنید
5. با اکانت عادی «خرید سرویس» را تست کنید

---

## نصب روی Windows

```powershell
git clone https://github.com/Mrclocks/PGClockBot.git
cd PGClockBot

python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
notepad .env

python run.py
```

وب‌پنل: [http://127.0.0.1:9000](http://127.0.0.1:9000)

---

## اجرای دائمی با systemd (لینوکس)

```bash
sudo nano /etc/systemd/system/pgclockbot.service
```

محتوا (مسیرها را عوض کنید):

```ini
[Unit]
Description=PGClockBot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/PGClockBot
Environment=PATH=/opt/PGClockBot/.venv/bin
ExecStart=/opt/PGClockBot/.venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pgclockbot
sudo systemctl status pgclockbot
```

لاگ:

```bash
journalctl -u pgclockbot -f
```

---

## تنظیم پلن‌های فروش (مهم)

منبع حقیقت حجم/زمان = **پاسارگارد**. بات فقط قیمت و تحویل را مدیریت می‌کند.

1. وارد داشبورد PasarGuard شوید
2. یک **User Template** بسازید (حجم، مدت، گروه‌ها)
3. ID تمپلیت را بردارید
4. در وب‌پنل بات → **پلن‌ها** → نام، قیمت، مدت، و `Template ID` را ذخیره کنید
5. در **تنظیمات** شماره کارت و نام صاحب کارت را وارد کنید

بدون `Template ID` هم می‌تواند یوزر بسازد (با حجم/مدت پلن)، ولی تمپلیت پیشنهادی است.

---

## نقش‌ها

### ادمین

- آیدی تلگرام در `ADMIN_IDS`
- دسترسی کامل بات + وب‌پنل

### نماینده

از بات (پنل ادمین) یا وب‌پنل → نمایندگان بسازید.

ورود وب برای نماینده:

| فیلد | مقدار |
|------|--------|
| نام کاربری | Telegram ID عددی |
| رمز | کد دعوت همان کاربر (`referral_code`) |

### کاربر عادی

با `/start` می‌تواند بخرد، کیف پول شارژ کند، سرویس ببیند و تیکت بزند.

اتصال سرویس موجود با لینک ساب:

```text
https://t.me/YourBotUsername?start=sub_TOKEN
```

---

## مینی‌اپ و Webhook (اختیاری)

برای مینی‌اپ، تلگرام **HTTPS عمومی** می‌خواهد.

1. دامنه را به سرور وصل کنید و SSL بگیرید (مثلاً Nginx + Certbot)
2. ریورس‌پراکسی به پورت `9000`:

```nginx
server {
    listen 443 ssl;
    server_name bot.example.com;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

3. در `.env`:

```env
PUBLIC_BASE_URL=https://bot.example.com
WEBHOOK_URL=https://bot.example.com
WEBHOOK_PATH=/telegram/webhook
```

4. سرویس را ری‌استارت کنید. دکمه مینی‌اپ در منوی ربات ظاهر می‌شود.

---

## ساختار پروژه

```text
PGClockBot/
├── app/
│   ├── bot/           # هندلرهای تلگرام
│   ├── api/           # FastAPI وب‌پنل + API مینی‌اپ
│   ├── web/           # قالب‌ها و استاتیک
│   ├── services/      # پاسارگارد، سفارش، کیف پول، ...
│   ├── db/            # مدل‌ها و دیتابیس
│   ├── jobs/          # اعلان انقضا/حجم
│   └── main.py
├── run.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## عیب‌یابی

| مشکل | کار پیشنهادی |
|------|----------------|
| ربات جواب نمی‌دهد | `BOT_TOKEN` و اتصال اینترنت را چک کنید؛ لاگ را ببینید |
| خطای لاگین پاسارگارد | `PG_BASE_URL` بدون اسلش انتهایی اضافه، یوزر/پسورد درست |
| خرید تحویل نمی‌شود | Template ID معتبر؟ دسترسی ادمین پنل کامل است؟ |
| وب‌پنل باز نمی‌شود | فایروال پورت `9000`، `WEB_HOST=0.0.0.0` |
| مینی‌اپ نیست | `PUBLIC_BASE_URL` با HTTPS ست شده باشد |

---

## امنیت

- فایل `.env` را هرگز در گیت commit نکنید
- رمز وب‌پنل و `WEB_SECRET` را عوض کنید
- در پروداکشن ترجیحاً پشت Nginx + HTTPS اجرا کنید
- دسترسی پنل پاسارگارد را محدود نگه دارید

---

## لایسنس

استفاده شخصی / تجاری طبق نیاز خودتان؛ اتصال فقط به API پنل PasarGuard.
