# PGClockBot

ربات فروش و مدیریت پنل **PasarGuard** — سبک، فارسی، با وب‌پنل روی پورت `9000` و مینی‌اپ تلگرام.

---

## امکانات

- خرید برای کاربر تازه‌وارد (پلن، کیف پول، کارت‌به‌کارت)
- سرویس من، تمدید، پشتیبانی، اعلان انقضا / اتمام حجم
- نقش **نماینده** (کمیسیون، تأیید رسید)
- پنل ادمین داخل بات + عملیات پاسارگارد
- وب‌پنل مدیریت مینیمال روی `:9000`
- مینی‌اپ تلگرام (با دامنه HTTPS)

---

## نصب آسان (Ubuntu 22.04+)

فقط روی **Ubuntu 22.04 و بالاتر** پشتیبانی می‌شود.

```bash
git clone https://github.com/Mrclocks/PGClockBot.git
cd PGClockBot
chmod +x install.sh update.sh
./install.sh
```

اسکریپت:

1. نسخه Ubuntu را چک می‌کند (کمتر از ۲۲ → توقف)
2. پیش‌نیازها را نصب می‌کند (`python3`, `venv`, `pip`, `git`, …)
3. سوال‌ها را **به انگلیسی** می‌پرسد (توکن، ادمین، پاسارگارد، یوزر/پسورد وب)
4. Mini App URL را می‌توانید **خالی Enter** بزنید
5. پسورد وب را با قانون امن اجباری می‌کند (۸+ / حرف بزرگ / کاراکتر خاص)
6. `.env` را با Python امن می‌نویسد
7. اختیاری systemd می‌سازد و ربات را اجرا می‌کند

---

## آپدیت بدون وارد کردن دوباره اطلاعات

`.env` دست نمی‌خورد؛ فقط کد و پکیج‌ها به‌روز می‌شوند:

```bash
cd PGClockBot
git pull
chmod +x update.sh
./update.sh
```

اگر فقط رمز وب‌پنل را عوض می‌خواهید (بدون نصب دوباره):

```bash
source .venv/bin/activate
python scripts/set_web_password.py
sudo systemctl restart pgclockbot
```

---

## پیش‌نیازها

| مورد | توضیح |
|------|--------|
| OS | **Ubuntu 22.04+** |
| پنل PasarGuard | API در دسترس |
| بات تلگرام | توکن از [@BotFather](https://t.me/BotFather) |
| آیدی عددی ادمین | از [@userinfobot](https://t.me/userinfobot) |

---

## تنظیم از وب‌پنل

`http://IP:9000` → ورود با یوزر/رمزی که در نصب ساختید → **تنظیمات**

| بخش | مثال |
|-----|------|
| عمومی و متن‌ها | خوش‌آمد، FAQ، راهنما |
| پرداخت و کانال | شماره کارت، عضویت اجباری |
| برچسب دکمه‌ها | خرید، کیف پول، پشتیبانی |
| چیدمان منو | classic / compact |
| پلن‌ها | قیمت + Template ID پاسارگارد |

---

## اگر وب‌پنل «رمز اشتباه» می‌گوید یا وارد نمی‌شوید

ورود وب از فایل جداگانه `data/web_admin.json` خوانده می‌شود (نه فقط `.env`).

1. سلامت پنل را چک کنید:
   ```bash
   curl http://127.0.0.1:9000/health
   ```
   باید `"ok": true` و `"admin_username"` را ببینید.
2. رمز را ریست کنید:
   ```bash
   cd PGClockBot
   source .venv/bin/activate
   python scripts/set_web_password.py
   sudo systemctl restart pgclockbot
   ```
3. فایروال را باز کنید: `sudo ufw allow 9000/tcp`
4. آدرس درست: `http://IP_SERVER:9000/login` (نه دامنه پاسارگارد)

---

## اگر ربات به /start جواب نمی‌دهد

1. لاگ را ببینید:
   ```bash
   journalctl -u pgclockbot -f
   # یا اگر دستی اجرا کرده‌اید خروجی ترمینال را ببینید
   ```
2. باید خطی شبیه این باشد: `Bot online as @YourBot …`
3. مطمئن شوید فقط **یک** پروسه ربات در حال اجراست
4. در BotFather بات را Disable / Enable کنید و دوباره `/start` بزنید
5. `ADMIN_IDS` را با آیدی عددی خودتان از `@userinfobot` چک کنید (نه یوزرنیم)

---

## نصب دستی (بدون اسکریپت)

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

در `.env` مقادیر دارای کاراکتر خاص را داخل کوتیشن بگذارید:

```env
WEB_ADMIN_PASSWORD="MyPass!A"
PG_PASSWORD="Secret#1"
```

---

## systemd

```bash
sudo systemctl enable --now pgclockbot
sudo systemctl status pgclockbot
journalctl -u pgclockbot -f
```

---

## مینی‌اپ (اختیاری)

دامنه HTTPS + ریورس‌پراکسی به پورت `9000`، سپس در `.env`:

```env
PUBLIC_BASE_URL="https://bot.example.com"
```

---

## امنیت

- `.env` را commit نکنید
- پسورد وب و `WEB_SECRET` را قوی نگه دارید
- در پروداکشن پشت Nginx + HTTPS اجرا کنید
