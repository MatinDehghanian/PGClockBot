# Roadmap اجرای وضعیت اتصال در PGClockBot

تاریخ: ۲۰۲۶/۱۰/۱۵. مبنا: `upstream/dev` و [سند پژوهش](CONNECTION_STATUS_RESEARCH.md).
وضعیت: **مرحله‌های صفر تا چهار انجام شدند؛ مراحل پنج تا هشت باز هستند و runtime پایش هنوز فعال نیست.**
[قرارداد رفتار](CONNECTION_STATUS_CONTRACT.md) و [baseline ثبت‌شده](CONNECTION_STATUS_BASELINE.md)
خروجی مرحلهٔ صفر هستند.

هدف PR: ادمین اصلی از داخل ربات هاست‌های فعال را برای تست واقعی اتصال انتخاب کند،
نتیجه را ببیند و در صورت تمایل، هر مورد را با نام عمومی مستقل به مشتری نمایش دهد.
تست اولیه از سرور خود ربات انجام می‌شود و فقط همان یک پنل PasarGuard منبع اطلاعات است.

## ۱. محدودهٔ PR و ترتیب تحویل

- انتخاب هاست، روشن/خاموش کردن پایش، اجرای دستی، تنظیم انتشار و نام عمومی داخل ربات.
- اجرای Xray کلاینت مجزا با حساب پایش موجود؛ بدون استفاده از حساب یا حجم مشتری.
- تست دوره‌ای HTTPS از مسیر کانفیگ، نتیجهٔ ذخیره‌شده و تشخیص نتیجهٔ قدیمی.
- ابتدا تکمیل مسیر ادمین؛ سپس فعال کردن نمایش مشتری با انتشار پیش‌فرض خاموش.
- پشتیبانی SQLite و PostgreSQL، دسترسی Owner صریح، scope فروشگاه و تست‌های امنیتی.
- راهنمای نصب core، تنظیم حساب پایش، عیب‌یابی و توقف قابلیت.

مدیریت توسط نماینده، worker داخل ایران، زنجیرهٔ پروکسی واسط، تست سرعت دانلود، اعلان
انبوه، تاریخچهٔ طولانی، Mini App و صفحهٔ جدید وب در این PR نیستند. `probe_id=local`
در مدل نتیجه از ابتدا ثبت می‌شود تا افزودن نقطهٔ تست آینده به تغییر معنای نتایج نیاز نداشته باشد.

این مراحل، commitهای متوالی یک قابلیت هستند؛ تست هر بخش هم‌زمان با همان بخش نوشته
می‌شود. مرحلهٔ نمایش مشتری وابسته به قبولی مسیر ادمین است.

## ۲. انتخاب کتابخانه‌ها و ابزارها

انتخاب‌ها بر اساس تناسب با معماری و وابستگی‌های فعلی‌اند. وابستگی Python جدید برای
نسخهٔ اول لازم نیست؛ نصب خودکار «آخرین نسخه» هم جزو جریان اجرای ربات نیست.

| بخش | انتخاب | کاربرد و تصمیم |
| --- | --- | --- |
| اجرای پروتکل | binary رسمی Xray-core | اجرای کانفیگ واقعی؛ نسخه و checksum ثابت در ماتریس سازگاری ثبت شود |
| HTTP از پروکسی | `httpx.AsyncClient` فعلی | پروکسی HTTP محلی، CONNECT برای HTTPS، TLS معتبر و client قابل بازاستفاده |
| deadline و هم‌زمانی | `asyncio` در Python 3.12 | `timeout`، `Semaphore` و `create_subprocess_exec` بدون shell |
| دیتابیس | SQLAlchemy 2 async و درایورهای فعلی | query محدود، transaction کوتاه و claim اتمیک |
| migration | Alembic فعلی | upgrade تکرارپذیر، indexها و downgrade |
| ورودی و DTO | Pydantic v2 و `dataclass` استاندارد | اعتبارسنجی مرزی strict و دادهٔ داخلی typed |
| زمان‌بندی | APScheduler فعلی در شاخهٔ 3.x | job مستقل از Telegram؛ جلوگیری محلی از overlap و coalesce |
| رابط ربات | aiogram 3 فعلی | Router مستقل، FSM و helperهای safe موجود |
| حفاظت اسرار | `secret_box.py` و `redact.py` موجود | عدم ساخت رمزنگاری یا sanitization موازی |
| تست | pytest، `unittest.IsolatedAsyncioTestCase`، `AsyncMock` | سازگار با الگوی فعلی پروژه؛ بدون نیاز به افزونهٔ async جدید |
| شبیه‌سازی HTTP | `httpx.MockTransport` | پاسخ و خطای قابل‌کنترل، بدون شبکه |
| lint | Ruff و `scripts/lint_changed.sh` | رعایت ratchet موجود و محدودیت پیچیدگی |

HTTPX به‌صورت داخلی HTTP proxy دارد؛ SOCKS به وابستگی اختیاری نیاز دارد. برای این
قابلیت ورودی محلی HTTP انتخاب می‌شود و وابستگی SOCKS اضافه نمی‌شود.
[مستند پروکسی HTTPX](https://www.python-httpx.org/advanced/proxies/)

timeoutهای HTTPX برای connect/read/write/pool هستند و سقف کل عمر عملیات نیستند؛
هر درخواست باید deadline جدا با `asyncio.timeout` هم داشته باشد. تعداد connectionها
با `Limits` و تعداد تست‌های فعال با semaphore محدود شود.
[timeoutهای HTTPX](https://www.python-httpx.org/advanced/timeouts/)،
[محدودیت منابع](https://www.python-httpx.org/advanced/resource-limits/)،
[deadline در Python 3.12](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.timeout)

`AsyncSession` بین taskهای موازی share نشود. خروجی شبکه DTO باشد و هر واحد ذخیره‌سازی
session مستقل و کوتاه داشته باشد.
[مستند SQLAlchemy async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks)

در PR اجرایی فقط برای وابستگی‌های مستقیماً مرتبط، حد بالا اضافه شود:
`httpx>=0.28,<1` و `apscheduler>=3.10,<4`. نسخه‌های دقیق واقعاً آزمایش‌شده در نتیجهٔ CI
ثبت شوند؛ dependency upgrade عمومی انجام نشود. نسخهٔ binary Xray در مرحلهٔ ۱ و بر
اساس تست سازگاری انتخاب شود، نه با حدس شمارهٔ آخرین release.

## ۳. جریان اجرای قابلیت پس از پیاده‌سازی

1. Owner حساب موجود و اختصاصی پایش را یک بار به قابلیت متصل می‌کند؛ secret از پنل
   گرفته و در صورت نیاز رمز‌شده نگهداری می‌شود. برای هر هاست config دستی وارد نمی‌شود.
2. ربات فهرست هاست‌های فعال و مجاز را نشان می‌دهد؛ ادمین موارد لازم را انتخاب می‌کند.
3. تنظیم پایش، انتشار، نام عمومی و ترتیب به‌صورت محلی ذخیره می‌شود؛ remark پنل تغییر نمی‌کند.
4. job مستقل از Telegram، حق اجرای دور را در دیتابیس claim و transaction را commit می‌کند.
5. اطلاعات هاست/حساب یک بار خوانده و endpointهای مشخص هر هاست به outbound معتبر نگاشت می‌شوند.
6. Xray با ورودی محلی جدا برای endpointها اجرا و آمادگی واقعی آن بررسی می‌شود.
7. درخواست HTTPS از همان مسیر ارسال می‌شود؛ فقط پاسخ مورد انتظار موفق محسوب می‌شود.
8. نتیجه با کنترل lease، نسخهٔ تنظیمات و وضعیت فعال ذخیره و وضعیت هاست محاسبه می‌شود.
9. ادمین جزئیات امن را می‌بیند؛ مشتری فقط نام عمومی، وضعیت، زمان و محل بررسی را می‌بیند.
10. بروزرسانی صفحهٔ مشتری فقط snapshot را می‌خواند؛ اجرای دستی ادمین درخواست در صف است.

## ۴. مراحل توسعه و دروازه‌های پذیرش

| مرحله | خروجی قابل بررسی | پیش‌نیاز | معیار عبور |
| --- | --- | --- | --- |
| ۰ | ✅ baseline و قرارداد رفتار | — | scope، وضعیت‌ها و baseline تست ثبت شده باشند |
| ۱ | نگاشت هاست به کانفیگ و fixtureها | ۰ | مسیر هر هدف بدون ابهام و بدون fallback مستقیم ثابت شود |
| ۲ | مدل داده، migration و permission | ۱ | تکرار upgrade، downgrade، scope و claim روی دو DB قبول شوند |
| ۳ | مدیریت امن process Xray | ۱ | start، readiness، timeout، cancellation و cleanup پوشش داده شوند |
| ۴ | تست HTTPS و سیاست سلامت | ۰ و ۳ | نتیجهٔ قابل‌تکرار، deadline واقعی و خطای امن داشته باشد |
| ۵ | job، lease و ذخیرهٔ نتایج | ۲ و ۴ | اجرای هم‌زمان، crash و نتیجهٔ دیررس سلامت را خراب نکنند |
| ۶ | مدیریت ادمین در ربات | ۵ | انتخاب، تست دستی و تنظیم انتشار با مجوز درست کار کنند |
| ۷ | فهرست وضعیت مشتری | ۶ | فقط موارد عمومی همان shop و نتیجهٔ معتبر نمایش داده شوند |
| ۸ | سازگاری استقرار و آماده‌سازی PR | همه | تست‌ها، مقایسه با dev، lint و آزمایش استقرار ثبت شوند |

### مرحلهٔ ۰ — قرارداد و baseline

- [x] پیش از کدنویسی، آخرین `upstream/dev` و head مهاجرت‌ها دوباره بررسی شود.
- [x] baseline suite و security suite در checkout تمیز همان کامیت ثبت شود؛ خروجی‌ها
  بیرون مخزن بمانند و failureهای شناخته‌شده با تغییر جدید قاطی نشوند.
- [x] وضعیت‌های `healthy`، `degraded`، `down`، `unknown`، `not_ready` و `paused` تعریف شوند.
- [x] تفاوت مشاهدهٔ ادمین با خروجی عمومی و الزامی بودن عبارت «بررسی از سرور ربات» ثبت شود.
- [x] پیش‌فرض‌ها، قرارداد account و ماتریس transportهای قابل پشتیبانی مشخص شوند.

معیار پذیرش: حالت اولیه، freshness، شکست مشترک و بازیابی پس از قطعی قابل تبدیل به
جدول تست باشند؛ هیچ «سبز بودن» مبهمی باقی نماند.

### مرحلهٔ ۱ — اثبات نگاشت و محدودهٔ پشتیبانی

- [x] fixtureهای مصنوعی host، inbound، حساب پایش و خروجی Xray ساخته شوند؛ هیچ secret
  واقعی یا payload خام production در fixture قرار نگیرد.
- [x] خروجی ساختاریافتهٔ پنل معتبر خوانده شود؛ ترتیب لیست و `remarks` کلید هویت نباشند.
- [x] نگاشت `pg_host_id → endpoint_key → outbound` بر اساس تنظیمات مؤثر انجام شود.
- [x] endpointهای چندآدرسی، tagهای کمکی و routeهای وابسته صریحاً محاسبه و محدود شوند.
- [x] ظرفیت در زمان انتخاب و sync بر اساس endpoint شمرده شود؛ افزایش تعداد آدرس‌های
  یک host نتواند سقف را دور بزند. هدف خارج ظرفیت با دلیل امن مشخص شود و سالم فرض نشود.
- [x] ترکیب ناشناخته، نگاشت مبهم یا پوشش ناقص `not_ready` شود و درخواست شبکه ایجاد نکند.
- [x] ماتریس نخست با اولویت VLESS + Reality و VLESS + TLS/WebSocket بررسی شود؛ هر
  ترکیب فقط پس از fixture و تست core وارد فهرست پشتیبانی شود. بقیهٔ پروتکل‌ها بر اساس
  نیاز واقعی هاست‌ها و همان معیار اضافه شوند، نه با fallback حدسی.

معیار پذیرش: دو هاست متمایز به مسیر خود بروند، تغییر ترتیب یا نام نتیجه را جابه‌جا
نکند و کانفیگ تولیدشده مسیر مستقیم جایگزین نداشته باشد. نبودن این اثبات مانع شروع UI است.

### مرحلهٔ ۲ — داده، مجوز و مرزهای هم‌زمانی

پیشنهاد اجرایی مدل نسبت به طرح اولیهٔ پژوهش دو تکمیل دارد: یک ردیف وضعیت runtime برای
lease سراسری و snapshot جدا برای هر endpoint. نام نهایی با convention فعلی تطبیق داده شود.

| مدل | مسئولیت و قیود اصلی |
| --- | --- |
| `ConnectionMonitorState` | scope، فعال بودن قابلیت، مرجع حساب پایش و نسخهٔ آن، lease دور اجرا؛ cooldown دستی در target است. برای runner اولیه ردیف شناخته‌شدهٔ `local` |
| `ConnectionMonitorTarget` | scope، شناسهٔ host پنل، flags، نام/ترتیب، نسخهٔ اندازه‌گیری، due و claim هدف؛ unique هر host در همان scope |
| `ConnectionMonitorSnapshot` | target، `endpoint_key`، `probe_id`، نسل کانفیگ، وضعیت و دلیل، زمان‌ها، مقصد، delay و حداکثر پنج نمونه؛ unique این سه شناسه |

- [x] shop از principal/context معتبر گرفته شود؛ همهٔ queryها و mutationها scope داشته باشند.
- [x] یکتایی shop اصلی با `reseller_id IS NULL` با partial unique جدا روی SQLite و PostgreSQL
  رعایت شود؛ unique مرکب معمولی با NULL کافی نیست.
- [x] indexهای فهرست scope، due، lease و lookup snapshot در model و migration باشند.
- [x] migration از head زمان اجرای PR ساخته شود؛ شمارهٔ فعلی رزرو نشود. هر create/index
  قابل اجرای مجدد باشد، ستون NOT NULL default داشته باشد و downgrade داده‌های قبلی پروژه را حفظ کند.
- [x] `connection_status` و `connection_status_manage` به `FEATURE_PERMS` اضافه شوند؛
  نماینده‌ها پیش‌فرض مجوز نگیرند و Owner صریح جدا از `can_shop` بررسی شود.
- [x] داده‌های محرمانه وارد snapshot نشوند؛ شکست رمزنگاری/بازگشایی حساب را `not_ready` کند.

هر worker lease سراسری `local` را قبل از شروع core بگیرد تا سقف concurrency در چند
process هم حفظ شود. claim هدف و token نتیجه جدا باقی بمانند تا اجرای دستی، توقف و
تغییر تنظیمات قابل کنترل باشد. expiry از بودجهٔ دور و زمان cleanup بیشتر باشد؛
دور منقضی اجازهٔ ذخیرهٔ نتیجه نداشته باشد.

### مرحلهٔ ۳ — lifecycle هستهٔ Xray

- [x] core فقط از مسیر مطلق مورد اعتماد و نسخهٔ تأییدشده اجرا شود؛ قابلیت خاموش، binary نخواهد.
- [x] core به ازای batch اجرا شود؛ برای هر tap یا هر درخواست HTTP process جدید ساخته نشود.
- [x] config از allow-list outboundهای تأییدشده ساخته شود؛ API، inbound و routing دلخواه
  موجود در اشتراک اجرا نشوند. ورودی‌ها فقط loopback باشند.
- [x] تخصیص پورت و برخورد bind با retry محدود مدیریت شود؛ باز بودن یک پورت قدیمی اثبات
  آمادگی core جدید نباشد. process باید زنده باشد و ورودی متعلق به اجرای جاری باشد.
- [x] فایل موقت با مجوز محدود، فایل‌خوانی در thread، argv بدون secret و stdout/stderr
  با مصرف محدود و بدون ذخیرهٔ payload خام باشند.
- [x] start/readiness/shutdown deadline داشته باشند؛ در cancellation، terminate، سپس در
  صورت نیاز kill و در پایان wait انجام شود. taskهای جانبی و فایل‌ها هم جمع شوند.
- [x] رفتار crash سخت والد و پاک‌سازی فرزندان با سیاست process group/systemd استقرار
  بررسی شود؛ صرف `finally` تضمین cleanup پس از SIGKILL نیست.

مستند استاندارد برای اجرای async process و نیاز به timeout جدا:
[Python subprocess](https://docs.python.org/3.12/library/asyncio-subprocess.html).

### مرحلهٔ ۴ — سنجش و طبقه‌بندی سلامت

- [x] `AsyncClient` محدود به همان پروکسی محلی با `trust_env=False`، بدون redirect،
  TLS verification روشن، HTTP/2 خاموش و بدون retry پنهان ساخته شود.
- [x] client به ازای endpoint در batch بازاستفاده شود؛ keep-alive HTTP برای روش
  `fresh_http` بسته شود. mux داخلی Xray با ادعای اتصال کاملاً سرد اشتباه نشود.
- [x] برای پاسخ 204 از streaming استفاده شود و body نامنتظره دانلود نامحدود نشود؛
  response در همهٔ مسیرها بسته شود. زمان network از صف و startup جدا باشد.
- [x] دو مقصد ثابت HTTPS داشته باشیم؛ مقصد دوم فقط پس از شکست اول، از همان پروکسی تست شود.
- [x] کنترل مستقیم، تشخیص خرابی مشترک باشد و هرگز نتیجهٔ موفق جایگزین نسازد؛ timeoutهای
  کنترل هم داخل بودجهٔ کل دور باشند و کنترل مشترک به ازای هر host تکرار نشود.
- [x] طبقه‌بندی تابعی مستقل از DB/Telegram باشد و زمان و نتیجهٔ قبلی ورودی صریح آن باشند.

قرارداد دقیق نمونه‌برداری و وضعیت:

| رخداد | نتیجه |
| --- | --- |
| نخستین نمونهٔ معتبر موفق با پوشش کامل | `healthy`؛ مگر delay از آستانه عبور کرده باشد |
| اولین/دومین دور شکست معتبر مسیر | `degraded` |
| سه دور متوالی شکست معتبر مسیر، با حساب و کنترل سالم | `down` |
| اولین موفقیت بعد از اختلال/قطعی | `degraded`؛ دومین دور موفق به شرط کیفیت و پوشش، `healthy` |
| حساب/runner/کانفیگ نامعتبر یا علت مشترک نامعلوم | `not_ready` یا `unknown`؛ شکست به حساب host نوشته نشود |
| وقفهٔ نامعلوم بین نمونه‌ها | streak موفقیت/شکست قطع شود؛ نتیجهٔ قدیمی فقط برای جزئیات ادمین بماند |
| نسل قدیمی، نمونهٔ مفقود یا stale در یکی از endpointهای لازم | host نتواند `healthy` شود؛ وضعیت مؤثر `unknown` |
| همهٔ endpointها سالم | host سالم؛ شکست بخشی از آن‌ها `degraded` و قطعی معتبر همه `down` |

نمونهٔ timeout مقدار delay ساختگی نگیرد. میانهٔ حداکثر پنج نمونهٔ موفق فقط از همان
نسل، endpoint، مقصد و پنجرهٔ freshness محاسبه شود. تغییر روش یا حساب، نمونه‌های قبلی
را از محاسبه خارج کند. نام عمومی و ترتیب، به‌تنهایی نسل اندازه‌گیری را تغییر ندهند.

### مرحلهٔ ۵ — worker و scheduler

- [ ] job با شناسهٔ ثابت در `start_background_scheduler` ثبت شود؛ نبود Telegram پایش را متوقف نکند.
- [ ] `max_instances=1` و `coalesce=True` تنظیم شوند؛ قفل واقعی چندprocess در DB باشد.
  [مستند APScheduler 3.x](https://apscheduler.readthedocs.io/en/3.x/userguide.html)
- [ ] claim قبل از network commit شود؛ session هنگام اجرای core یا HTTP باز نماند.
- [ ] catalog و حساب در batch خوانده شوند؛ فهرست محلی LIMIT و keyset داشته باشد.
- [ ] در اجرای موازی هر ذخیره‌سازی session مستقل داشته باشد؛ semaphore با تعداد
  endpoint فعال کار کند، نه فقط تعداد hostها.
- [ ] نتیجه فقط با token معتبر، نسل فعلی، target فعال و lease منقضی‌نشده نوشته شود.
- [ ] حذف/غیرفعال شدن host یا تغییر تنظیمات مؤثر، نسل را عوض و نتایج قبلی را نامعتبر کند.
- [ ] خطای یک هدف، دور را متوقف نکند. اتمام بودجه، توقف یا crash runner به‌عنوان قطعی
  host ثبت نشود؛ freshness در زمان خواندن هم محاسبه شود، حتی اگر scheduler دیگر اجرا نشود.
- [ ] تست دستی همان مسیر صف و claim را طی کند؛ tap تکراری فقط یک درخواست pending بسازد.

پیش‌فرض اولیه: interval برابر ۶۰ ثانیه، deadline هر درخواست پنج ثانیه، concurrency چهار،
حداکثر ۱۲ endpoint مؤثر فعال، بودجهٔ کل دور ۵۰ ثانیه و stale پس از ۱۸۰ ثانیه.
این محدودیت‌ها ابتدا تنظیم استقرار با اعتبارسنجی باشند؛ UI تنظیمات بی‌نیاز اضافه نشود.
بودجه شامل panel read، core readiness، fallback و cleanup است. هدف نرسیده به نوبت،
timeout جعلی نگیرد. در سقف اولیه، سه گروه چهار‌تایی با دو مقصد، حداکثر ۳۰ ثانیه
زمان درخواست پروکسی می‌خواهند؛ ۲۰ ثانیهٔ باقی‌مانده سهم خواندن پنل، startup، کنترل مشترک
و cleanup است. deadline کاری باید سهم cleanup را حفظ کند. افزایش ظرفیت به محاسبه و
اندازه‌گیری مجدد نیاز دارد؛ ترتیب due باید اجازه ندهد عقب‌ماندگی، اهداف انتهای فهرست را گرسنه نگه دارد.

### مرحلهٔ ۶ — رابط ادمین

- [ ] Router مدیریتی مستقل با middleware Owner فعلی و کنترل مجوز داخل service اضافه شود.
- [ ] فهرست هاست فعال، انتخاب، توقف، «بررسی اکنون»، نام عمومی و ترتیب با FSM روشن پیاده شود.
- [ ] قبل از ذخیره، وضعیت host و scope دوباره بررسی شود؛ به لیست قبلی یا callback اعتماد نشود.
- [ ] نام عمومی هنگام انتشار الزامی، trimmed و حداکثر ۶۴ نویسه باشد؛ عددها strict و محدود باشند.
- [ ] خاموش کردن پایش، انتشار را هم خاموش کند؛ فعال شدن دوباره، آن را خودکار منتشر نکند.
- [ ] وضعیت اجرا، نتیجهٔ اولیه، پوشش ناقص، خطای امن و زمان آخرین بررسی نمایش داده شوند.
- [ ] label و متن قابل‌ویرایش از تنظیمات و `safe_format` فعلی عبور کنند؛ callback کوتاه
  و helperهای `safe_edit_text` و back/cancel موجود استفاده شوند.

### مرحلهٔ ۷ — رابط مشتری

- [ ] Router عمومی جدا از Router دارای middleware Owner ثبت شود تا مشتری مسدود نشود.
- [ ] shop فقط از context معتبر ربات تعیین شود؛ ورودی مشتری scope دلخواه نسازد.
- [ ] فقط موارد فعال و منتشرشدهٔ همان shop با نام عمومی و ترتیب پایدار خوانده شوند.
- [ ] خروجی عمومی DTO مستقل داشته باشد و هیچ فیلد داخلی/secret از ORM مستقیماً render نشود.
- [ ] HTML نام‌ها escape و زمان/عدد با formatter مشترک نمایش داده شود.
- [ ] حالت بدون مورد عمومی، بدون نتیجه، stale و خطای خواندن امن داشته باشد.
- [ ] بروزرسانی مشتری هیچ panel call، core start یا درخواست آزمایش ایجاد نکند.

انتشار قبل از نمونهٔ اول می‌تواند «نامشخص» نشان دهد، ولی نیازمند config پشتیبانی‌شده
و نام معتبر است. delay عددی در خروجی اولیهٔ مشتری نمایش داده نشود؛ ادمین آن را می‌بیند.

## ۵. سازمان‌دهی کد

ماژول‌ها به‌اندازهٔ نیاز ساخته شوند؛ این فهرست مجوز ایجاد لایهٔ عمومی یا فایل خالی نیست.

| مسیر پیشنهادی | مسئولیت |
| --- | --- |
| `app/services/connection_status_types.py` | DTOها، enumها و قراردادهای داده |
| `app/services/connection_monitor_catalog.py` | catalog مجاز و نگاشت host/endpoint |
| `app/services/connection_monitor_config.py` | ساخت config محدود و اعتبارسنجی وابستگی tagها |
| `app/services/xray_probe.py` | lifecycle process و ورودی‌های محلی |
| `app/services/connection_probe.py` | درخواست HTTP و نتیجهٔ اندازه‌گیری |
| `app/services/connection_status_policy.py` | وضعیت، freshness، streak و تجمیع endpointها |
| `app/services/connection_status.py` | use caseهای انتخاب، انتشار، claim و snapshot |
| `app/jobs/connection_status.py` | orchestration batch؛ قواعد داخل service بمانند |
| `app/bot/handlers/connection_status_admin.py` | ورودی و نمایش مدیریتی |
| `app/bot/handlers/connection_status.py` | فهرست عمومی |
| `app/db/models.py` و migration جدید | فقط مدل‌ها و قیود مرتبط |

اصول کدنویسی این PR:

- تابع typed، مسئولیت مشخص، حدود ۴۰ خط و پیچیدگی حداکثر ۱۵؛ ماژول حدود ۱۵۰ خط که
  رشد کرد بر اساس مسئولیت شکسته شود، بدون بازنویسی بخش‌های قدیمی نامرتبط.
- DTO داخلی `dataclass(slots=True, frozen=True)` و ورودی مرزی با Pydantic strict؛
  callback/FSM ابتدا parse محدود و سپس validate شوند. [strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)
- وابستگی `bot/jobs → services → db`؛ هیچ service از FastAPI یا aiogram import نکند.
- تزریق ساعت، process factory و transport فقط در مرزهای لازم برای تست؛ abstraction
  جدید پنل، generic repository یا framework اجرای task ساخته نشود.
- خطای مورد انتظار domain error باشد؛ خرابی DB با rollback و خطای نهایی با log امن ثبت شود.
- handler فقط parse، authorize، یک use case و render؛ handler جدید در `reply_nav.py` قرار نگیرد.
- حالت fallback، retry و cleanup صریح و محدود باشد؛ `except: pass` و logging secret ممنوع.

## ۶. برنامهٔ تست خودکار

نام فایل‌ها پیشنهادی است؛ assertions باید رفتار را ثابت کنند، نه وجود رشته یا چیدمان source.

| فایل تست | سناریوهای الزامی |
| --- | --- |
| `test_connection_monitor_catalog.py` | فقط host فعال/مجاز؛ host مفقود؛ قطع پنل؛ تغییر ترتیب؛ چندآدرس؛ mapping مبهم؛ محدودیت تعداد endpoint |
| `test_connection_monitor_config.py` | حفظ Reality/SNI/path/flow؛ route دو هدف مستقل؛ tag کمکی؛ رد outbound/route نامعتبر؛ ممنوعیت fallback مستقیم و آدرس خارج allow-list |
| `test_xray_probe.py` | binary مفقود/ناسازگار؛ شروع ناموفق؛ readiness timeout؛ bind conflict؛ process قدیمی؛ cancellation؛ terminate/kill/wait؛ cleanup و خروجی حجیم |
| `test_connection_probe.py` | فقط 204 مورد انتظار موفق؛ رد 200/redirect/500؛ TLS/timeout؛ deadline کل در برابر read تدریجی؛ fallback همان پروکسی؛ بسته شدن response؛ عدم retry پنهان |
| `test_connection_status_policy.py` | جدول تمام انتقال‌ها؛ سه شکست؛ دو موفقیت بازیابی؛ قطع streak با unknown؛ stale؛ تغییر نسل/مقصد؛ میانهٔ پنج نمونه؛ تجمیع host چندendpoint |
| `test_connection_status.py` | تنظیم معتبر؛ نام خالی/طولانی/HTML؛ bool و عدد نامعتبر؛ قطع انتشار با توقف؛ عدم تغییر پنل؛ یکتایی و rollback پس از خطای DB |
| `test_connection_status_concurrency.py` | دو session مستقل و barrier؛ رقابت worker/تست دستی؛ یک claim برنده؛ lease سراسری؛ expiry؛ token قدیمی؛ تغییر config و disable حین اجرا؛ نتیجهٔ تکراری |
| `test_connection_status_authz.py` | Owner معتبر؛ role=admin بدون principal؛ permission مفقود؛ principal غیرفعال؛ shop دوم؛ مشتری دوم؛ callback دستکاری‌شده؛ حساب پایش خارج scope |
| `test_connection_status_bot.py` | FSM انتخاب/نام/انتشار؛ back/cancel؛ tap تکراری؛ callback فوری؛ پاسخ امن به پیام حذف‌شده؛ pagination؛ اسرار در پیام یا log نباشند |
| `test_connection_status_public.py` | فقط موارد عمومی همان shop؛ escape نام؛ payload بدون آدرس و secret؛ empty/stale/error؛ cache/DTO جدا؛ بروزرسانی بدون فراخوانی runner یا پنل |
| `test_connection_status_runtime.py` | سقف concurrency و ظرفیت؛ بودجهٔ دور؛ خطای یک هدف؛ shutdown؛ catalog قدیمی؛ خاموش بودن قابلیت؛ عدم اثر پایش بر سفارش/کیف پول/تحویل |
| `test_connection_status_migration.py` | upgrade دیتابیس موجود، upgrade دوم، downgrade و حفظ rows قبلی؛ indexها، defaultها و unique دامنهٔ NULL روی هر دو DB |

علاوه بر فایل‌های جدید، `test_scheduler_background_jobs.py` باید ثبت job جدید، استقلال
از Telegram، شروع تکراری بدون duplicate و shutdown را پوشش دهد. تغییر شمار jobها
فقط با انتظار صحیح رفتار جدید انجام شود؛ تست موجود حذف یا ضعیف نشود.

### زیرساخت و مرز اعتبار تست‌ها

- unit/service با SQLite حافظه‌ای و fake panel اجرا شوند. رقابت DB از SQLite فایل موقت
  با connection/session مستقل استفاده کند؛ دو task روی یک session اثبات concurrency نیست.
- همان قرارداد migration/claim روی PostgreSQL موقت محلی از Unix socket اجرا شود؛
  DB production یا credential واقعی استفاده نشود. job سازگاری CI باید این محیط را
  آماده کند و نبود پیش‌نیاز را failure اعلام کند، نه تست سبز با skip.
- core در job سازگاری از نسخهٔ تأییدشده آماده شود؛ config مصنوعی با حالت validation
  core بررسی شود. unit suite به نصب core وابسته نباشد.
- تمام تست‌های خودکار بدون اتصال شبکه به Telegram، پنل یا اینترنت باشند؛ HTTP با
  MockTransport و process با fake قابل کنترل پوشش داده شود.
  [مستند MockTransport](https://www.python-httpx.org/advanced/transports/#mock-transports)
- MockTransport عبور واقعی از CONNECT/Xray را ثابت نمی‌کند؛ این بخش با آزمایش مجزای
  استقرار انجام و صریحاً از نتیجهٔ unit test جدا گزارش شود.
- ساعت و timeout با clock قابل تزریق و event/barrier کنترل شوند؛ sleep طولانی یا تست
  مبتنی بر زمان‌بندی تصادفی ساخته نشود. زمان‌سنجی real deadline با margin مشخص باشد.

فایل‌های دارای authorization، tenancy، secret، route safety و claim حتماً در
`scripts/security_test_manifest.txt` ثبت شوند؛ حداقل فایل‌های config، xray، authz،
status، concurrency، bot و public از این ویژگی در CI پوشش داشته باشند.

تست مشتری دوم دربارهٔ تنظیمات و نتایج خصوصی است؛ دو مشتری مجاز در یک shop باید
هر دو بتوانند همان فهرست منتشرشدهٔ عمومی را ببینند.

## ۷. اعتبارسنجی کارایی و استقرار

قبل از معرفی عمومی، این شواهد ثبت شوند:

- [ ] فهرست عمومی صفر panel call و صفر core start داشته باشد؛ query count برای تعداد
  endpointهای متفاوت افزایش خطی نکند و لیست LIMIT داشته باشد.
- [ ] در ظرفیت ۱۲ endpoint، concurrency از چهار بالاتر نرود و deadline دور رعایت شود؛
  بیش از ظرفیت با پیام روشن رد شود و هیچ host انتخاب‌شده بی‌صدا از برنامه حذف نشود.
- [ ] ۱۰۰ بروزرسانی مشتری درخواست تست جدید ایجاد نکنند؛ زمان و query count واقعی ثبت شوند.
- [ ] query plan فهرست due، lookup snapshot و ترتیب عمومی روی دیتابیس نمونه بررسی شود.
- [ ] روی staging، یک کانفیگ درست موفق و UUID نامعتبر، توقف core و مسیر مسدود ناموفق باشند؛
  دسترسی مستقیم سرور به مقصد نتواند خطای کانفیگ را پنهان کند.
- [ ] خرابی مقصد اول با مقصد دوم، انقضای حساب، قطع پنل و قطع worker به وضعیت درست برسند.
- [ ] یک چرخهٔ قطع و بازیابی، تغییر نام، توقف تست و حذف/خاموش کردن host در UI بررسی شوند.
- [ ] مصرف CPU/RAM و تعداد process/فایل/پورت پیش و پس از batch و cancellation ثبت شوند.
- [ ] restart سرویس و دو process هم‌زمان، job یا child اضافهٔ پایدار ایجاد نکنند.

آزمایش staging از سرور ربات و فقط با حساب پایش انجام شود. نبود حساب یا binary اجازهٔ
گزارش «تست زنده موفق» نمی‌دهد؛ در این حالت PR می‌تواند draft باشد ولی gate استقرار تکمیل نیست.

## ۸. ترتیب commitها و آماده‌سازی PR

| ترتیب | موضوع commit | همراه همان commit |
| --- | --- | --- |
| ۱ | `feat: resolve monitored hosts to validated Xray routes` | قرارداد، mapping، fixture و تست آن |
| ۲ | `feat: persist connection monitor settings and claims` | مدل، migration، permission و تست DB/isolation |
| ۳ | `feat: run isolated Xray connection probes` | core lifecycle، HTTP و تست process/timeout |
| ۴ | `feat: schedule and reconcile connection status checks` | سیاست سلامت، job، lease، freshness و تست رقابت |
| ۵ | `feat: manage monitored hosts from the admin bot` | FSM، مجوز، نام عمومی و تست ربات |
| ۶ | `feat: show published connection status to customers` | نمایش scopeشده و تست عمومی |
| ۷ | `docs: explain connection monitor setup and operation` | راهنما، ماتریس سازگاری و شواهد نهایی |

اگر یک مرز اجرایی ایجاب کرد، commitهای مرتبط می‌توانند کوچک‌تر شوند؛ commit مربوط به
رفتار بدون regression test آمادهٔ تحویل محسوب نشود. baseline failure واقعاً اشتباه
در commit جدا اصلاح و دلیل آن توضیح داده شود.

فرمان‌های بررسی پس از ایجاد فایل‌های برنامه‌ریزی‌شده:

```bash
python -m pytest tests/test_connection_*.py tests/test_xray_probe.py tests/test_scheduler_background_jobs.py -q
bash scripts/run_security_tests.sh
bash scripts/lint_changed.sh upstream/dev
python -m pytest tests -q -p no:cacheprovider
git diff --check
```

job سازگاری PostgreSQL/core نیز جدا اجرا و نتیجه‌اش ضمیمه شود. در این PR فایل browser
قرار نیست تغییر کند؛ اگر دامنه به JavaScript گسترش یافت، Node regression test همان
منطق و بررسی CSP/escaping هم لازم است.

توضیح نهایی PR علیه آخرین `dev` شامل این موارد باشد:

- مشکل و رفتار جدید، مسیر اجرا، مدل داده و نحوهٔ کنترل concurrency/failure.
- migration و head نهایی، permissionها، تنظیمات و پیش‌نیاز Xray/حساب پایش.
- پروتکل/transportهای واقعاً پشتیبانی‌شده و محدودیت تست از سرور ربات.
- تعداد واقعی passed/failed/skipped برای focused/security/full و تفاوت با baseline تمیز؛
  هیچ failure جدید مجاز نیست و skip پیش‌نیاز gate سازگاری، جای قبولی را نگیرد.
- نسخه‌های آزمایش‌شده، شواهد staging و کارایی؛ نتیجهٔ انجام‌نشده موفق اعلام نشود.
- محدوده‌های تعمداً خارج PR و روش توقف/بازگشت عملیاتی.

فعال‌سازی تدریجی: قابلیت پیش‌فرض خاموش → اتصال حساب و یک host خصوصی → پایش چند دور
و بررسی failure/recovery → افزایش تا ظرفیت تأییدشده → انتشار انتخابی با نام عمومی.
rollback عملیاتی با خاموش کردن worker و انتشار و cleanup core انجام شود؛ schema و
داده‌های قبلی پروژه برای برگشت برنامه حفظ شوند. `VERSION` و release notes تغییر نکنند.

## ۹. نقطهٔ شروع

مرحلهٔ صفر با قرارداد و baseline ثبت‌شده تکمیل شد. مرحلهٔ یک نیز انجام شد:
نگاشت و fixtureهای دو هاست مستقل با ۷۰ تست و validation رسمی core تکمیل شدند؛
[ماتریس سازگاری](CONNECTION_STATUS_COMPATIBILITY.md) محدودیت‌های دقیق را ثبت می‌کند.
مرحلهٔ ۲ هم با migration `0054_connection_monitor`، مجوز Owner، مرجع رمز‌شدهٔ حساب و
leaseهای runtime/target روی SQLite و PostgreSQL تکمیل شد. مرحلهٔ ۳ با ۱۲ تست lifecycle، پنج زیرتست و اجرای سه مسیر مصنوعی روی core رسمی macOS
تکمیل شد. مرحلهٔ ۴ هم با سنجش HTTPS محدود به پروکسی، کنترل مقصد، سیاست خالص وضعیت و ۲۳ تست
به‌همراه ۲۵ زیرتست تکمیل شد. مرحلهٔ بعد worker و ذخیرهٔ امن نتیجه است؛ آزمایش Linux و
اتصال زنده همچنان gate استقرار هستند.
