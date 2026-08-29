# PGClockBot v8.8.0 — Release Notes

**Tag:** `v8.8.0`  
**App version:** `8.8.0`  
**Restore point:** tag `restore/pre-v8.8.0-v8.7.9` (@ `v8.7.9`)

---

## Settlement Core (افزایشی + امن)

1. **Additive** — کارت/درگاه‌لینک/رمزارز/استارز/کیف‌پول دست‌نخورده
2. **موتور واحد + آداپتر** — `payment_settlement` + `payment_providers`
3. **Fail-closed** — بدون verify و تطبیق مبلغ، تحویل نیست
4. **Signed webhook + idempotent + amount match + audit** — جدول `payment_settlements`
5. **UI پنل + تست بدون مرچنت** — فقط با `ALLOW_SETTLEMENT_MOCK=1` + توکن یک‌بارمصرف

### امنیت / ایزوله نقش‌ها

- Mock پیش‌فرض **خاموش** (`ALLOW_SETTLEMENT_MOCK=0`)؛ settle فقط با توکن یک‌بارمصرف
- وب‌هوک کارت: مسیر جدا `platform` و `shop/{reseller_id}` — secret همان tenant
- `payment_id` الزامی؛ بدون match مبلغ سراسری
- `shop_owner_id` روی settlement؛ مرچنت/رمز به‌صورت `password` (خالی = بدون تغییر)
- provider پیش‌فرض: `zarinpal` (نه mock)
- شارژ کیف‌پول با PSP و تنظیمات ربات هم‌تراز پنل
- Race/idempotency: SAVEPOINT به‌جای `session.rollback`؛ فقط یک webhook مالک SETTLING و یک‌بار `approve_payment`

### Deploy

مایگریشن: `0021_payment_settlements` (شامل `shop_owner_id` + `checkout_token` + partial unique indexes).

Hard refresh once. SW بدون تغییر اجباری (`pgclock-shell-v47`).
