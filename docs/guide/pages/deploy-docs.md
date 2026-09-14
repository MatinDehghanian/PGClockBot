---
id: deploy-docs
---

## راهنما را روی دامنه خودتان بالا بیاورید

خروجی آماده در پروژه اینجاست:

`app/web/static/guide/`

همین پوشه یک سایت استاتیک کامل است (HTML/CSS/JS/فونت).

## روش ۱ — آپلود روی هاست

1. داخل پروژه:
```bash
python scripts/build_guide.py
```
2. محتویات `app/web/static/guide/` را روی هاست دامنه خودتان بریزید.
3. دامنه را به همان پوشه اشاره دهید؛ مثلاً `https://docs.example.com`

## روش ۲ — Nginx روی VPS

```nginx
server {
  listen 80;
  server_name docs.example.com;
  root /var/www/pgclock-docs;
  index index.html;
  location / {
    try_files $uri $uri/ $uri/index.html =404;
  }
}
```

محتویات `guide/` را در `/var/www/pgclock-docs` کپی کنید.

## وصل کردن آیکون ؟ پنل به دامنه شما

در `.env` سرور ربات:

```env
DOCS_BASE_URL="https://docs.example.com"
```

سرویس را ری‌استارت کنید. از این به بعد لینک‌های راهنمای داخل پنل به دامنه شما می‌روند.

:::tip
اگر `DOCS_BASE_URL` خالی باشد، همان `/help` روی سرور کاربر استفاده می‌شود.
:::

:::info
بعد از هر تغییر در فایل‌های `docs/guide/pages/` باید دوباره `python scripts/build_guide.py` را اجرا کنید و خروجی را هم در گیت/سرور docs آپدیت کنید.
:::
