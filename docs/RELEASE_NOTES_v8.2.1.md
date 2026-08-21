# PGClockBot v8.2.1 — Release Notes

**Tag:** `v8.2.1`  
**App version:** `8.2.1`  
**Restore point:** tag `restore/pre-bot-settings-menus-v8.2.0` (@ `v8.2.0`)

---

## منوی تنظیمات ربات — ساده‌سازی امن

- هاب تنظیمات مالک و نماینده یکدست شد: **فروشگاه · منو · پرداخت · پشتیبان‌ها · دسترسی · اعلان‌ها**
- نماینده: بخش **ربات** (فقط توکن فروشگاه خودش؛ توکن پلتفرم رد می‌شود)
- دکمه **وب‌پنل** برای ظاهر / رنگ / گزارش روزانه / متن‌های بلند
- پلن تست و نام‌گذاری از کیبورد تنظیمات خارج شد (مسیر پلن‌ها / پنل باقی است)
- رنگبندی دکمه‌ها با هاب جدید هم‌تراز (`adm_st_access` / `*_st_panel`؛ alias قدیمی `adm_st_service`)
- ACL قبلی Owner / `shop_settings` و ایزوله فروشگاه حفظ شد

## Deploy

In-panel update to `8.2.1` (no new migration). Hard-refresh the panel after update.
