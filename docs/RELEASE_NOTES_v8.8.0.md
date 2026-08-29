# PGClockBot v8.8.0 — Release Notes

**Tag:** `v8.8.0`  
**App version:** `8.8.0`  
**Restore point:** tag `restore/pre-v8.8.0-v8.7.9` (@ `v8.7.9`)

---

## Settlement Core (افزایشی)

پنج شرط رعایت شده:

1. **Additive** — کارت/درگاه‌لینک/رمزارز/استارز/کیف‌پول دست‌نخورده؛ دو کانال جدید کنار آن‌ها
2. **موتور واحد + آداپتر** — `payment_settlement` + `payment_providers` (mock / zarinpal / card-auto)
3. **Fail-closed** — بدون verify موفق و تطبیق مبلغ، تحویل نمی‌شود
4. **Signed webhook + idempotent + amount match + audit** — جدول `payment_settlements`، HMAC وب‌هوک، کلید ایدمپوتنسی
5. **UI پنل + تست بدون مرچنت** — تنظیمات تب پرداخت؛ Mock checkout در `/payments/settlement/mock/checkout`

### کانال‌ها

- **درگاه آنلاین API (`pay_psp`)** — provider=`mock` (پیش‌فرض تست) یا `zarinpal` (با مرچنت)
- **تأیید خودکار کارت (`pay_card_auto`)** — وب‌هوک `POST /payments/settlement/card-auto/webhook` با هدر `X-Signature`

### Deploy

مایگریشن: `0021_payment_settlements`.

Hard refresh once. SW بدون تغییر اجباری (`pgclock-shell-v47`).
