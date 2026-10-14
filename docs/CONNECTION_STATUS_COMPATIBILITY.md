# سازگاری نگاشت وضعیت اتصال

مرحلهٔ ۱ روی Xray **26.3.27**، commit `d2758a0`، در macOS/arm64 اعتبارسنجی شد.
منبع binary، [release رسمی v26.3.27](https://github.com/XTLS/Xray-core/releases/tag/v26.3.27)
و فایل `Xray-macos-arm64-v8a.zip` است. SHA-256 آرشیو پیش از استخراج و اجرا با digest
release تطبیق داده شد:

```text
2e93a67e8aa1936ecefb307e120830fcbd4c643ab9b1c46a2d0838d5f8409eaf
```

ورودی نگاشت، فهرست کامل هاست‌های همان principal، `inbounds/details` و خروجی native
Xray حساب اختصاصی پایش است. API جزئیات inbound برای VLESS اطلاعات Reality/TLS را
ندارد؛ بنابراین بازسازی آن از فیلدهای حدسی انجام نمی‌شود. قرارداد پنل بر اساس
[schema هاست](https://github.com/PasarGuard/panel/blob/b56ffe369f542152c52c69733205baeaf3f6e4cd/app/models/host.py)،
[خلاصهٔ inbound](https://github.com/PasarGuard/panel/blob/b56ffe369f542152c52c69733205baeaf3f6e4cd/app/operation/system.py)
و [خروجی بومی Xray](https://github.com/PasarGuard/panel/blob/b56ffe369f542152c52c69733205baeaf3f6e4cd/app/subscription/xray.py)
بررسی شد. کد generator پنل کپی نشده است.

نگاشت از آدرس، پورت، protocol/network اینباند و overrideهای صریح security/SNI/Host/path
استفاده می‌کند. همهٔ هاست‌های catalog، حتی انتخاب‌نشده‌ها، در تشخیص ابهام حضور دارند.
`remark`، ترتیب لیست و ترتیب نمونه‌های اشتراک هیچ نقشی در هویت ندارند. UUID و تنظیمات
TLS/Reality از outbound معتبر خود پنل حفظ می‌شوند.

برای دامنهٔ اولیه، هر هاست باید **پورت صریح و دقیقاً یک SNI ثابت** داشته باشد. SNI
پیش‌فرض نامعلوم، انتخاب چند پورت، wildcard، placeholder و چند SNI تأیید نشده‌اند.
نبود این پیش‌نیازها نتیجهٔ `not_ready` است؛ ربات تنظیم هاست پنل را تغییر نمی‌دهد.

| ترکیب | شواهد مرحلهٔ ۱ | محدودیت |
| --- | --- | --- |
| VLESS + Reality + TCP خام | fixture، حفظ UUID/flow/key/SNI/short ID و `xray run -test` موفق | encryption=`none`؛ flow خالی یا Vision؛ بدون dialer/mux/fragment |
| VLESS + TLS + WebSocket | fixture، حفظ SNI/Host/path/ALPN و `xray run -test` موفق | TLS verification روشن؛ flow خالی؛ تنظیم‌های پیشرفته خارج ماتریس |
| چند آدرس ثابت | ساخت مسیر مستقل برای هر آدرس و اعتبارسنجی کانفیگ سه‌مسیره | ثابت بودن سایر تنظیم‌ها و نبود تطبیق مبهم برای تمام آدرس‌ها |
| tag کمکی، fragment/noise، mux، XHTTP، template سفارشی هاست | تست رد صریح | تا اثبات مستقل `not_ready` |

کانفیگ runtime از نو با ورودی HTTP روی `127.0.0.1` ساخته می‌شود. اولین outbound
`blackhole` است و هر ورودی فقط به outbound منتخب خودش route دارد. routing، DNS،
ورودی‌ها و outboundهای مستقیم template اشتراک وارد runtime نمی‌شوند. وجود `dialerProxy`،
`proxySettings` یا فیلد ناشناخته در outbound اصلی باعث رد آن می‌شود.

در چندآدرسی، تنها آدرس outbound یکتای ثابت با آدرس‌های صریح همان هاست جایگزین می‌شود؛
بقیهٔ تنظیمات ثابت می‌مانند. اگر آدرس گسترش‌یافته به چند هاست بخورد، یا دو نمونهٔ native
برای یک هاست تنظیم متفاوت داشته باشند، هیچ مسیر ناقصی برای آن هاست ساخته نمی‌شود.
بیش از ۱۲ endpoint، تمام انتخاب آماده را با دلیل ظرفیت متوقف می‌کند؛ حذف بی‌صدای هدف نداریم.

فایل `tests/fixtures/connection_monitor_catalog.json` کاملاً مصنوعی است؛ UUID آن حساب
واقعی نیست. ۷۰ تست بدون شبکه و بدون credential واقعی اجرا شدند. کانفیگ حاصل شامل
دو endpoint Reality و یک endpoint WebSocket با `xray run -test -config …` بررسی شد.
این اثبات syntax و پذیرش core است؛ اتصال واقعی، عبور CONNECT، نصب Linux و دسترسی از
سرور ربات هنوز gate جداگانهٔ استقرارند. Xray هنگام validation دربارهٔ deprecation
WebSocket پیام می‌دهد؛ پشتیبانی این ماتریس به نسخهٔ بررسی‌شده محدود است.

نگاشت یک تابع خالص است. دریافت authenticated catalog، تأیید حساب اختصاصی و فعال بودن
آن، authorization صریح Owner، نگهداری secret و TTL به use case و worker مراحل بعد تعلق
دارند. هیچ job، دکمه یا پایش فعال در مرحلهٔ ۱ اضافه نشده است.
