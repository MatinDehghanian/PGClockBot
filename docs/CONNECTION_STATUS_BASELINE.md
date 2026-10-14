# baseline مرحلهٔ صفر وضعیت اتصال

تاریخ اجرا: ۲۰۲۶/۱۰/۱۵. مرجع تمیز `upstream/dev`:
`2c53456186932a31eb8a0fad9c1fdfbeb6ed99de`.
head تأییدشدهٔ Alembic: `0051_service_import`.

این گزارش همراه [قرارداد رفتار](CONNECTION_STATUS_CONTRACT.md)، خروجی مرحلهٔ صفر
[roadmap](CONNECTION_STATUS_ROADMAP.md) است. گزارش وضعیت اجرای ربات یا نتیجهٔ تست
اتصال زنده نیست.

## روش اجرا و محیط

یک checkout تمیز از dev و یک checkout مستقل از شاخهٔ Draft با اسناد مرحلهٔ صفر
آزمایش شدند. هر دو از یک virtualenv موقت با وابستگی‌های `requirements-dev.txt`
استفاده کردند؛ requirements مخزن و محیط Python اصلی تغییر نکردند. مقایسهٔ محتوای
`app`، `tests`، `scripts` و `alembic` یکسان بودن فایل‌های اجرایی و تست را تأیید کرد.

محیط: macOS / arm64، Python `3.12.5`، Node `22.16.0` و Bash `5.3.20`.

| وابستگی | نسخهٔ آزمایش‌شده |
| --- | --- |
| pytest / Ruff | `9.1.1` / `0.17.0` |
| aiogram | `3.31.0` |
| FastAPI / Starlette | `0.143.1` / `1.8.0` |
| SQLAlchemy / Alembic | `2.1.4` / `1.20.0` |
| HTTPX | `0.28.1` |
| Pydantic | `2.13.5` |
| APScheduler | `3.11.3` |

`pip check` ناسازگاری نصب گزارش نکرد. لاگ، JUnit XML، فهرست کامل بسته‌ها و محیط تست
خارج مخزن نگهداری شدند؛ این سند خلاصهٔ نتایج است و آن فایل‌ها وارد commit نمی‌شوند.

## نتایج

ترتیب عددها در جدول: **موفق / شکست / skip**.

| بررسی | dev تمیز | Draft مرحلهٔ صفر | شکست جدید در Draft |
| --- | --- | --- | --- |
| full suite | ۴۰۸۳ / ۷۸ / ۵ | ۴۰۸۳ / ۷۸ / ۵ | صفر |
| security manifest، ۱۲۳ فایل | ۱۵۸۸ / صفر / صفر | ۱۵۸۸ / صفر / صفر | صفر |
| focused، سه فایل مرتبط | ۱۱۴ / صفر / صفر | ۱۱۴ / صفر / صفر | صفر |

full suite در هر دو checkout علاوه بر شمارش جدول، ۱۸۸ subtest موفق داشت. تعداد subtest جدا از
تعداد تست‌های اصلی گزارش می‌شود تا با شمارش testcaseهای JUnit مخلوط نشود.

فهرست دقیق ۷۸ شکست full suite در دو اجرا یکسان بود؛ هیچ failure یا error جدیدی
در Draft دیده نشد. مجموعهٔ امنیتی و focused در هر دو اجرا بدون شکست یا skip تمام
شدند. مجموعهٔ امنیتی در هر اجرا ۱۷۲ subtest و focused در هر اجرا ۱۱ subtest موفق داشتند.
پس از اجرا فقط گزارش و نشانگر پیشرفت اسناد نهایی شدند؛ کد، تست و وابستگی تغییر نکردند.

نمونهٔ خانواده‌های شکست موجود در dev، با شمارش full suite:

- `test_reply_chrome_remainders_0_2_12.py`: پنج شکست.
- `test_bot_settings_hub_simplify.py`: چهار شکست.
- `test_commission_stepper_adjust_c861.py`: چهار شکست.
- `test_delete_submit_reason_from_ops.py`: چهار شکست.
- `test_bot_button_labels_in_settings.py`: سه شکست.

این موارد در این مرحله اصلاح یا از اجرا حذف نشدند. کار اجرایی بعدی باید نتیجهٔ
خود را با همین مرجع و نسخه‌های وابستگی، یا baseline تازهٔ dev زمان شروع آن، مقایسه کند.

## فرمان‌ها

```bash
python -m pytest tests -q -p no:cacheprovider --tb=short
bash scripts/run_security_tests.sh -p no:cacheprovider --tb=short
python -m pytest tests/test_scheduler_background_jobs.py tests/test_service_live_info.py tests/test_customer_features.py -q -p no:cacheprovider --tb=short
python -m alembic heads
bash scripts/lint_changed.sh upstream/dev
git diff --check upstream/dev
```

گزینهٔ JUnit در اجرای واقعی به مسیر موقت بیرون مخزن اشاره کرد. focused شامل scheduler،
خواندن اطلاعات زندهٔ سرویس و customer features است؛ هنوز تست مخصوص runtime این قابلیت
وجود ندارد، چون پیاده‌سازی آن در مرحلهٔ بعد آغاز می‌شود.

## محدودیت‌ها و مرز ادعا

پنج skip از کد موجود بودند: دو تست Playwright به‌دلیل نصب نبودن آن و سه تست PostgreSQL
به‌دلیل نبود دیتابیس آزمایشی. skip یا ضعف جدیدی به تست‌ها اضافه نشد. این اجرا تأیید
سازگاری PostgreSQL محسوب نمی‌شود؛ gate دیتابیس محلی مستقل در مرحلهٔ اجرایی لازم است.

این نتیجه از محیط macOS است؛ نتیجهٔ CI لینوکس باید جدا بررسی شود. Xray و حساب پایش
واقعی استفاده نشدند، transport تأیید اجرایی نگرفت و هیچ feature، مجوز، migration یا
تنظیم اجرایی جدیدی فعال نشد. موارد باقی‌ماندهٔ مراحل یک تا هشت در roadmap باز هستند.
