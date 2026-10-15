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
این اثبات syntax و پذیرش core است؛ اتصال واقعی، عبور CONNECT و دسترسی از
سرور ربات در این تحویل skip شده‌اند. Xray هنگام validation دربارهٔ deprecation
WebSocket پیام می‌دهد؛ پشتیبانی این ماتریس به نسخهٔ بررسی‌شده محدود است.

نگاشت یک تابع خالص است. دریافت authenticated catalog، تأیید حساب اختصاصی و فعال بودن
آن، authorization صریح Owner، نگهداری secret و TTL به use case و worker مراحل بعد تعلق
دارند. هیچ job، دکمه یا پایش فعال در مرحلهٔ ۱ اضافه نشده است.

## lifecycle مرحلهٔ ۳

همان binary رسمی روی macOS/arm64 با سه مسیر مصنوعی اجرا شد؛ پیام شروع خود child
دریافت، زنده بودن آن بررسی و سپس terminate و wait انجام شد. SHA-256 فایل اجرایی:

```text
5d9dd24c0aba4b6cfcc6a33a5d67f854816ee17f392bf932ec8176da46f7e404
```

runner مسیر مطلق بدون symlink، executable بودن، مجوز غیرقابل‌نوشتن برای group/other،
checksum و نسخهٔ دقیق `26.3.27` را پیش از تست بررسی می‌کند. فایل JSON در دایرکتوری
موقت `0700` و با مجوز `0600` ساخته می‌شود؛ I/O فایل به thread منتقل شده است.
environment هسته محدود، argv فاقد config خام و stdout/stderr بدون ذخیره یا log مصرف
می‌شوند. هیچ generator یا کد شخص ثالث کپی نشده و dependency تازه‌ای اضافه نشده است.

آمادگی به پورت باز وابسته نیست: طبق [Start در core نسخهٔ ثابت](https://github.com/XTLS/Xray-core/blob/v26.3.27/core/xray.go)،
پیام شروع پس از موفقیت همهٔ featureها صادر می‌شود. runner همان marker را از pipe
پردازش جاری با حافظهٔ محدود می‌خواند و exit را هم کنترل می‌کند. شکست bind حداکثر سه
بار با پورت‌های تازه تکرار می‌شود؛ نسخهٔ نادرست اصلاً وارد این retry نمی‌شود.

startup/readiness پنج ثانیه و terminate دو ثانیه مهلت دارند؛ سپس kill و wait حداکثر
دو ثانیه اجرا می‌شوند. لغو هنگام spawn، readiness یا کار، child و فایل‌ها را پاک می‌کند.
در SIGKILL والد، `finally` اجرا نمی‌شود: استقرار Linux باید با systemd و
`KillMode=control-group` تمام فرزندان را هنگام توقف سرویس جمع کند. `start_new_session`
جایگزین این سیاست نیست. پس از crash، فایل موقت ممکن است تا cleanup سیستم باقی بماند؛
مجوز محدود آن حفظ می‌شود و اپراتور می‌تواند دایرکتوری‌های `pgclock-probe-*` متعلق به
سرویس متوقف‌شده را حذف کند. این مورد تضمین پاک‌سازی پس از SIGKILL نیست.

۱۲ تست آفلاین و پنج زیرتست، شروع ناموفق، readiness بدون marker، child مرده، retry
محدود، خروجی حجیم، اختلاف نسخه/checksum، cancellation تکراری هنگام spawn و
terminate/kill/wait را پوشش می‌دهند. startup روی Linux نیز در CI تأیید شد؛ اتصال واقعی
با test user در سرور مقصد در این تحویل skip شده است.

## بررسی تکرارپذیر CI

workflow مستقل [Connection monitoring compatibility](../.github/workflows/connection-monitor.yml)
تست‌های رفتاری را روی PostgreSQL 16 و startup را با core رسمی Linux/amd64 اجرا می‌کند.
آرشیو Linux `Xray-linux-64.zip` با نسخهٔ ثابت `v26.3.27` و SHA-256 منتشرشده بررسی می‌شود:

```text
23cd9af937744d97776ee35ecad4972cf4b2109d1e0fe6be9930467608f7c8ae
```

پس از تأیید آرشیو، checksum فایل استخراج‌شده به runner داده می‌شود. CLI
`python -m app.cli.connection_monitor --binary /absolute/path/xray --sha256 …`
سه مسیر مصنوعی همین fixture را اجرا و readiness و reap شدن child را کنترل می‌کند؛
درخواست relay یا حساب واقعی استفاده نمی‌شود. مسیر fixture مربوط به checkout توسعه است.
پیکربندی PostgreSQL سرویس CI از [الگوی رسمی GitHub](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers)
پیروی می‌کند و حساب آن فقط متعلق به کانتینر موقت تست است.

اجرای محلی همین CLI روی macOS/arm64: سه endpoint، startup برابر `0.0924s`، cleanup
برابر `0.0025s` و بیشینهٔ RSS فرزندان `29664 KiB` ثبت شد. اعداد مربوط به startup مصنوعی
در این محیط هستند؛ ظرفیت و اتصال production هنوز اندازه‌گیری نشده‌اند.

[job تأیید Linux/amd64](https://github.com/Mrclocks/PGClockBot/actions/runs/38719627589/job/116370700334)
با Python 3.12.15 نیز پاس شد: سه endpoint، startup برابر `0.049s`، cleanup برابر
`0.0007s`، بیشینهٔ RSS فرزندان `35612 KiB` و child جمع‌شده ثبت شد. checksum آرشیو
رسمی پیش از اجرا تأیید شد. این نتیجه فقط mapping، پذیرش کانفیگ، readiness و cleanup
را پوشش می‌دهد؛ سنجش HTTPS زنده از حساب اختصاصی هنوز انجام نشده است.

unit ساخته‌شده توسط نصب‌کنندهٔ پروژه `KillMode` را override نمی‌کند؛ طبق
[مستند systemd](https://github.com/systemd/systemd/blob/main/man/systemd.kill.xml)
پیش‌فرض آن `control-group` است. override واحد سرویس روی سرور مقصد و جمع شدن child
پس از crash سخت باید در پذیرش استقرار بررسی شوند؛ به `finally` پس از SIGKILL تکیه نمی‌شود.
